from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.property import Property, UnitEPC, Comparable, Analysis
from src.data_sources.epc import EPCClient, validate_unit_count_from_epcs, calculate_avg_epc_rating
from src.data_sources.land_registry import LandRegistryClient
from src.data_sources.planning import analyze_planning_context
from src.analysis.ai_analysis import AnalysisEngine
from src.analysis.scoring import calculate_opportunity_score, calculate_title_split_score
from src.analysis.cost_calculator import analyze_cost_benefit
from src.analysis.valuation import estimate_individual_unit_values

logger = structlog.get_logger()


async def enrich_pending_properties(batch_size: int = 20) -> dict:
    """
    Enrich properties that haven't been analysed yet.

    Pipeline:
    1. Fetch EPC data
    2. Fetch Land Registry comparables
    3. Run AI analysis
    4. Calculate scores and costs
    5. Update property record
    """
    results = {
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "errors": [],
    }

    async with AsyncSessionLocal() as session:
        # Get pending properties
        query = select(Property).where(
            Property.status == "pending_enrichment"
        ).order_by(Property.first_seen.desc()).limit(batch_size)

        result = await session.execute(query)
        properties = list(result.scalars().all())

        for property in properties:
            try:
                await enrich_property(session, property)
                results["succeeded"] += 1
            except Exception as e:
                logger.error(
                    "Enrichment failed",
                    property_id=str(property.id),
                    error=str(e),
                )
                results["failed"] += 1
                results["errors"].append({
                    "property_id": str(property.id),
                    "error": str(e),
                })
            results["processed"] += 1

        await session.commit()

    logger.info("Enrichment batch complete", **results)
    return results


async def enrich_property(session: AsyncSession, property: Property) -> None:
    """Run full enrichment pipeline for a single property."""
    logger.info("Enriching property", property_id=str(property.id), postcode=property.postcode)

    # Mark as in progress
    property.status = "analysing"
    await session.flush()

    # 1. Fetch EPC data
    epcs = await fetch_epc_data(session, property)

    # 2. Fetch Land Registry comparables
    comparables = await fetch_comparables(session, property)

    # 3. Analyze planning context
    planning = analyze_planning_context(property.postcode, property.title or "")

    # 4. Run AI analysis (if we have enough data)
    analysis_result = None
    if property.estimated_units and property.estimated_units >= 2:
        try:
            engine = AnalysisEngine()
            analysis_result = await engine.analyze_property(
                property=property,
                description=property.title or "",
                epcs=epcs,
                comparables=comparables,
            )
        except Exception as e:
            logger.warning("AI analysis failed", error=str(e))

    # 5. Calculate valuations and costs
    if epcs:
        unit_valuations = await estimate_individual_unit_values(property, epcs, comparables)
        individual_values = [v.estimated_value for v in unit_valuations]

        if individual_values:
            cost_benefit = analyze_cost_benefit(
                asking_price=property.asking_price,
                num_units=len(individual_values),
                individual_values=individual_values,
            )

            property.estimated_individual_values = {
                "units": [
                    {"address": v.unit_address, "value": v.estimated_value}
                    for v in unit_valuations
                ]
            }
            property.estimated_split_costs = cost_benefit.costs.total
            property.estimated_gross_uplift = cost_benefit.benefits.gross_uplift
            property.estimated_net_uplift = cost_benefit.benefits.net_uplift

    # 6. Calculate final scores
    if analysis_result:
        property.opportunity_score = calculate_opportunity_score(
            property, analysis_result, epcs, comparables
        )
        property.title_split_score = calculate_title_split_score(property, analysis_result)

        # Create analysis record
        analysis = Analysis(
            property_id=property.id,
            analysis_type="detailed",
            title_structure_score=property.title_split_score,
            title_structure_notes={"tenure": analysis_result.tenure_analysis.likely_tenure},
            exit_strategy_score=0,
            financing_benefit_score=0,
            estimated_costs={"total": property.estimated_split_costs} if property.estimated_split_costs else None,
            estimated_benefits={"gross_uplift": property.estimated_gross_uplift} if property.estimated_gross_uplift else None,
            net_benefit_per_unit=property.estimated_net_uplift // property.estimated_units if property.estimated_net_uplift and property.estimated_units else None,
            risk_score=len(analysis_result.risk_analysis.red_flags) * 10,
            risk_factors={"red_flags": analysis_result.risk_analysis.red_flags},
            ai_summary=analysis_result.recommendation.rationale,
            ai_risk_flags={"red": analysis_result.risk_analysis.red_flags, "amber": analysis_result.risk_analysis.amber_flags},
            ai_confidence=analysis_result.unit_analysis.unit_confidence,
            recommendation=analysis_result.recommendation.action,
            recommendation_rationale=analysis_result.recommendation.rationale,
        )
        session.add(analysis)

    # Update status
    property.status = "analysed"
    property.last_analysed = datetime.utcnow()


async def fetch_epc_data(session: AsyncSession, property: Property) -> list:
    """Fetch and store EPC data for property."""
    client = EPCClient()

    try:
        epcs = await client.match_epcs_to_property(
            postcode=property.postcode,
            address_hint=property.address_line1,
        )

        if epcs:
            # Validate unit count
            validated_count, confidence = validate_unit_count_from_epcs(
                epcs, property.estimated_units or 0
            )
            property.epc_validated_units = validated_count

            # Calculate average EPC rating
            avg_rating, _ = calculate_avg_epc_rating(epcs)
            property.avg_epc_rating = avg_rating

            # Calculate total floor area
            total_sqft = sum(e.floor_area * 10.764 for e in epcs if e.floor_area)
            property.total_sqft = total_sqft

            # Store EPC records
            for epc in epcs:
                unit_epc = UnitEPC(
                    property_id=property.id,
                    unit_address=epc.address,
                    current_rating=epc.current_rating,
                    potential_rating=epc.potential_rating,
                    floor_area=epc.floor_area,
                    property_type=epc.property_type,
                    construction_age_band=epc.construction_age_band,
                    lodgement_date=epc.lodgement_date,
                    lmk_key=epc.lmk_key,
                )
                session.add(unit_epc)

        return epcs

    except Exception as e:
        logger.warning("EPC fetch failed", error=str(e))
        return []


async def fetch_comparables(session: AsyncSession, property: Property) -> list:
    """Fetch and store comparable sales data."""
    client = LandRegistryClient()

    try:
        sales = await client.get_comparable_sales(
            postcode=property.postcode,
            property_type="F",  # Flats
            months_back=24,
        )

        if sales:
            for sale in sales:
                comparable = Comparable(
                    property_id=property.id,
                    address=sale.address,
                    postcode=sale.postcode,
                    price=sale.price,
                    sale_date=sale.sale_date,
                    property_type=sale.property_type,
                    distance_meters=0,  # Would need geocoding
                    source="land_registry",
                )
                session.add(comparable)

        return sales

    except Exception as e:
        logger.warning("Comparables fetch failed", error=str(e))
        return []

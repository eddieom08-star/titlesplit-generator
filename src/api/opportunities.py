from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.property import Property, Analysis
from src.api.schemas import (
    OpportunityCard,
    OpportunityDetail,
    StrategyMemorandum,
    CostBreakdown,
    BenefitAnalysis,
    RiskAssessment,
    RiskItem,
    DueDiligenceItem,
    UnitDetail,
    FullAnalysis,
    ExecutiveSummary,
    CurrentStructureAnalysis,
    ProposedStructure,
    FinancialAnalysisDetail,
    ImplementationPlan,
    RiskAssessmentDetail,
    Appendices,
)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("", response_model=list[OpportunityCard])
async def list_opportunities(
    min_score: int = Query(default=60, ge=0, le=100),
    max_price: Optional[int] = Query(default=None),
    min_units: int = Query(default=2, ge=1),
    max_units: int = Query(default=10, le=50),
    cities: Optional[str] = Query(default=None, description="Comma-separated city names"),
    tenure: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    include_archived: bool = Query(default=False, description="Include archived properties"),
    sort_by: str = Query(default="score", enum=["score", "price", "date", "uplift"]),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    List title split opportunities.

    Returns summary cards for the deal feed.
    """
    # Build query conditions
    conditions = [
        Property.opportunity_score >= min_score,
        Property.estimated_units >= min_units,
        Property.estimated_units <= max_units,
    ]

    # Filter archived unless explicitly included
    if not include_archived:
        conditions.append(Property.archived == False)

    # Filter by status if provided, otherwise exclude rejected
    if status:
        conditions.append(Property.status == status)
    else:
        conditions.append(Property.status != "rejected")

    if max_price:
        conditions.append(Property.asking_price <= max_price)

    if cities:
        city_list = [c.strip().lower() for c in cities.split(",")]
        conditions.append(Property.city.ilike(f"%{city_list[0]}%"))

    if tenure:
        conditions.append(Property.tenure == tenure)

    # Build query
    query = select(Property).where(and_(*conditions))

    # Apply sorting
    if sort_by == "score":
        query = query.order_by(desc(Property.opportunity_score))
    elif sort_by == "price":
        query = query.order_by(Property.asking_price)
    elif sort_by == "date":
        query = query.order_by(desc(Property.first_seen))
    elif sort_by == "uplift":
        query = query.order_by(desc(Property.estimated_gross_uplift))

    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    properties = result.scalars().all()

    return [_property_to_card(p) for p in properties]


@router.get("/{property_id}", response_model=OpportunityDetail)
async def get_opportunity(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get full opportunity details.

    Includes all analysis, costs, benefits, and recommended actions.
    """
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    property = result.scalar_one_or_none()

    if not property:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    # Get latest analysis
    analysis_result = await db.execute(
        select(Analysis)
        .where(Analysis.property_id == property_id)
        .order_by(desc(Analysis.created_at))
        .limit(1)
    )
    analysis = analysis_result.scalar_one_or_none()

    return _property_to_detail(property, analysis)


@router.get("/{property_id}/report", response_model=StrategyMemorandum)
async def generate_report(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a Strategy Memorandum per Framework Section 9.

    Returns structured report matching framework output format.
    """
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    property = result.scalar_one_or_none()

    if not property:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    # Generate the full report
    return _generate_strategy_memorandum(property)


@router.post("/{property_id}/status")
async def update_status(
    property_id: UUID,
    status: str = Query(..., enum=["new", "analysing", "opportunity", "rejected", "contacted"]),
    db: AsyncSession = Depends(get_db),
):
    """Update opportunity status."""
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    property = result.scalar_one_or_none()

    if not property:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    property.status = status
    await db.commit()

    return {"status": "updated", "new_status": status}


def _property_to_card(property: Property) -> OpportunityCard:
    """Convert Property model to OpportunityCard response."""
    price_per_unit = 0
    if property.estimated_units and property.estimated_units > 0:
        price_per_unit = property.asking_price // property.estimated_units

    return OpportunityCard(
        id=property.id,
        source_url=property.source_url,
        title=property.title,
        price=property.asking_price,
        city=property.city,
        postcode=property.postcode,
        estimated_units=property.estimated_units or 0,
        price_per_unit=price_per_unit,
        opportunity_score=property.opportunity_score,
        tenure=property.tenure,
        tenure_confidence=property.tenure_confidence,
        avg_epc=property.avg_epc_rating,
        refurb_needed=bool(property.refurb_indicators),
        estimated_gross_uplift_percent=_calculate_uplift_percent(property),
        estimated_net_benefit_per_unit=_calculate_net_per_unit(property),
        recommendation=_get_recommendation(property),
        priority=_get_priority(property),
        first_seen=property.first_seen,
        images=[],  # Would come from relationship
    )


def _property_to_detail(property: Property, analysis: Optional[Analysis]) -> OpportunityDetail:
    """Convert Property model to OpportunityDetail response."""
    card = _property_to_card(property)

    # Build unit details from EPC data
    units = []
    if property.unit_breakdown:
        for i, unit in enumerate(property.unit_breakdown):
            units.append(UnitDetail(
                unit_identifier=f"Unit {i + 1}",
                beds=unit.get("beds"),
                floor_area_sqft=unit.get("sqft"),
                epc_rating=unit.get("epc"),
                estimated_value=unit.get("value"),
                value_confidence="medium",
            ))

    # Build cost breakdown
    estimated_costs = None
    if property.estimated_split_costs:
        estimated_costs = CostBreakdown(
            solicitor_fees=property.estimated_split_costs,
            land_registry_fees=0,
            title_plan_costs=0,
            lender_consent_fee=0,
            lender_legal_costs=0,
            valuation_fees=0,
            insurance_costs=0,
            contingency=0,
            total=property.estimated_split_costs,
            per_unit=property.estimated_split_costs // max(property.estimated_units or 1, 1),
        )

    # Build due diligence checklist
    due_diligence = [
        DueDiligenceItem(
            item="Verify freehold title",
            category="title",
            status="pending",
            action_required="Order official copies from Land Registry",
        ),
        DueDiligenceItem(
            item="Confirm single title",
            category="title",
            status="pending",
            action_required="Check title register for existing leases",
        ),
        DueDiligenceItem(
            item="Check planning status",
            category="legal",
            status="pending",
            action_required="Search council planning portal",
        ),
        DueDiligenceItem(
            item="Physical inspection",
            category="physical",
            status="pending",
            action_required="Arrange site visit",
        ),
    ]

    return OpportunityDetail(
        **card.model_dump(),
        description="",  # Would come from scraper
        key_features=[],
        agent_name=None,
        agent_phone=None,
        units=units,
        analysis=_build_full_analysis(analysis) if analysis else None,
        estimated_costs=estimated_costs,
        estimated_benefits=None,
        risks=_build_default_risk_assessment(),
        due_diligence=due_diligence,
        planning_portal_url=None,
        land_registry_search_url=f"https://www.gov.uk/search-property-information-land-registry",
        comparables=[],
    )


def _build_full_analysis(analysis: Analysis) -> FullAnalysis:
    """Build full analysis response from Analysis model."""
    return FullAnalysis(
        unit_analysis={},
        tenure_analysis={
            "score": analysis.title_structure_score,
            "notes": analysis.title_structure_notes,
        },
        condition_analysis={},
        financial_analysis={
            "estimated_costs": analysis.estimated_costs,
            "estimated_benefits": analysis.estimated_benefits,
            "net_benefit_per_unit": analysis.net_benefit_per_unit,
        },
        viability_analysis={
            "recommendation": analysis.recommendation,
            "rationale": analysis.recommendation_rationale,
            "risk_score": analysis.risk_score,
        },
    )


def _build_default_risk_assessment() -> RiskAssessment:
    """Build default risk assessment."""
    return RiskAssessment(
        overall_risk="medium",
        title_risk=RiskItem(level="medium", description="Title verification required"),
        lender_consent_risk=RiskItem(level="medium", description="Lender consent required"),
        boundary_risk=RiskItem(level="low", description="Standard boundary issues"),
        condition_risk=RiskItem(level="medium", description="Survey recommended"),
        market_risk=RiskItem(level="low", description="Stable market conditions"),
        red_flags=[],
        amber_flags=[],
        mitigation_strategies=[],
    )


def _calculate_uplift_percent(property: Property) -> Optional[int]:
    """Calculate gross uplift percentage."""
    if property.estimated_gross_uplift and property.asking_price:
        return int((property.estimated_gross_uplift / property.asking_price) * 100)
    return None


def _calculate_net_per_unit(property: Property) -> Optional[int]:
    """Calculate net benefit per unit."""
    if property.estimated_net_uplift and property.estimated_units:
        return property.estimated_net_uplift // property.estimated_units
    return None


def _get_recommendation(property: Property) -> str:
    """Get recommendation based on score."""
    if property.opportunity_score >= 75:
        return "proceed"
    elif property.opportunity_score >= 50:
        return "review"
    return "decline"


def _get_priority(property: Property) -> str:
    """Get priority based on score."""
    if property.opportunity_score >= 80:
        return "high"
    elif property.opportunity_score >= 60:
        return "medium"
    return "low"


def _generate_strategy_memorandum(property: Property) -> StrategyMemorandum:
    """Generate full strategy memorandum."""
    return StrategyMemorandum(
        generated_at=datetime.utcnow(),
        property_id=property.id,
        executive_summary=ExecutiveSummary(
            property_address=f"{property.address_line1}, {property.postcode}",
            recommendation=_get_recommendation(property),
            key_metrics={
                "asking_price": property.asking_price,
                "estimated_units": property.estimated_units,
                "opportunity_score": property.opportunity_score,
            },
            summary_rationale="Based on automated analysis of tenure, unit count, and market comparables.",
        ),
        current_structure=CurrentStructureAnalysis(
            tenure=property.tenure,
            title_details={"status": "verification_required"},
            unit_schedule=[],
            current_valuation=property.asking_price,
        ),
        proposed_structure=ProposedStructure(
            new_titles=[],
            lease_terms={"term_years": 999, "ground_rent": "peppercorn"},
            service_charge_structure={"management": "TBD"},
        ),
        financial_analysis=FinancialAnalysisDetail(
            costs=CostBreakdown(
                solicitor_fees=0,
                land_registry_fees=0,
                title_plan_costs=0,
                lender_consent_fee=0,
                lender_legal_costs=0,
                valuation_fees=0,
                insurance_costs=0,
                contingency=0,
                total=property.estimated_split_costs or 0,
                per_unit=0,
            ),
            benefits=BenefitAnalysis(
                current_value=property.asking_price,
                aggregate_individual_value=0,
                gross_uplift=property.estimated_gross_uplift or 0,
                gross_uplift_percent=0,
                transaction_costs=property.estimated_split_costs or 0,
                net_uplift=property.estimated_net_uplift or 0,
                net_uplift_percent=0,
                net_benefit_per_unit=0,
                meets_threshold=False,
                cost_ratio_acceptable=True,
            ),
            sensitivity_analysis={},
            break_even_analysis={},
        ),
        implementation_plan=ImplementationPlan(
            phases=[
                {"phase": 1, "name": "Due Diligence", "duration_weeks": 2},
                {"phase": 2, "name": "Legal Preparation", "duration_weeks": 4},
                {"phase": 3, "name": "Registration", "duration_weeks": 4},
            ],
            timeline_weeks=10,
            key_milestones=[],
            dependencies=["Title verification", "Lender consent"],
        ),
        risk_assessment=RiskAssessmentDetail(
            risk_matrix=[],
            mitigation_plan=[],
            residual_risks=[],
        ),
        appendices=Appendices(
            comparable_evidence=[],
            epc_data=[],
            planning_notes=None,
            title_notes=None,
        ),
    )

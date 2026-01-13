"""API endpoints for property details, manual inputs, and GDV reports."""
import base64
from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, HTTPException, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
import structlog

from src.database import AsyncSessionLocal
from src.models.property import Property, ManualInput
from src.services.propertydata import calculate_title_split_potential
from src.data_sources.land_registry import LandRegistryClient
from src.data_sources.epc import EPCClient
from src.analysis.gdv_calculator import GDVCalculator, BlockGDVReport, UnitValuation, ValuationConfidence
from src.analysis.floorplan_analyzer import FloorplanAnalyzer

logger = structlog.get_logger()
router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("/debug/schema")
async def debug_schema():
    """Debug endpoint to check database schema."""
    try:
        async with AsyncSessionLocal() as session:
            # Check what tables exist
            result = await session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            )
            tables = [row[0] for row in result.fetchall()]

            # Check manual_inputs columns if table exists
            mi_columns = []
            if "manual_inputs" in tables:
                col_result = await session.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name = 'manual_inputs'")
                )
                mi_columns = [row[0] for row in col_result.fetchall()]

            # Check alembic version
            alembic_version = None
            if "alembic_version" in tables:
                ver_result = await session.execute(text("SELECT version_num FROM alembic_version"))
                row = ver_result.fetchone()
                alembic_version = row[0] if row else None

            return {
                "tables": tables,
                "manual_inputs_columns": mi_columns,
                "alembic_version": alembic_version,
            }
    except Exception as e:
        return {"error": str(e), "error_type": type(e).__name__}


# Request/Response Models

class ManualInputUpdate(BaseModel):
    """Schema for updating manual verification data."""
    # Property Core Data (updates Property model directly)
    postcode: Optional[str] = None
    city: Optional[str] = None

    # Title Verification
    verified_tenure: Optional[str] = None
    title_number: Optional[str] = None
    is_single_title: Optional[bool] = None
    title_notes: Optional[str] = None

    # Unit Verification
    verified_units: Optional[int] = None
    unit_breakdown: Optional[list[dict]] = None

    # Planning Status
    planning_checked: Optional[bool] = None
    planning_constraints: Optional[dict] = None
    planning_notes: Optional[str] = None

    # HMO/Licensing
    hmo_license_required: Optional[bool] = None
    hmo_license_status: Optional[str] = None

    # Physical Inspection
    site_visited: Optional[bool] = None
    condition_rating: Optional[str] = None
    access_issues: Optional[str] = None
    structural_concerns: Optional[str] = None

    # Financial Adjustments
    revised_asking_price: Optional[int] = None
    additional_costs_identified: Optional[dict] = None
    negotiation_notes: Optional[str] = None

    # Deal Status
    deal_status: Optional[str] = None
    blockers: Optional[list[dict]] = None


class ImpactItem(BaseModel):
    """Single impact from a manual input."""
    field: str
    impact_type: str  # blocker, warning, positive, neutral
    score_adjustment: int
    message: str


class RecalculatedAnalysis(BaseModel):
    """Updated analysis after manual inputs."""
    property_id: str
    original_score: int
    adjusted_score: int
    original_recommendation: str
    updated_recommendation: str
    impacts: list[ImpactItem]
    confidence_level: str
    valuation: Optional[dict] = None
    cost_breakdown: dict
    net_benefit_per_unit: int
    blockers: list[dict]
    warnings: list[str]
    positives: list[str]


class PropertyDetail(BaseModel):
    """Full property details with manual inputs."""
    id: str
    source_url: str
    title: str
    asking_price: int
    city: str
    postcode: str
    estimated_units: int
    tenure: str
    tenure_confidence: float
    opportunity_score: int
    status: str
    first_seen: str
    # Manual inputs
    manual_inputs: Optional[dict] = None
    # Analysis
    analysis: Optional[dict] = None


class FloorplanAnalysisResponse(BaseModel):
    """Response from floorplan analysis."""
    units_detected: int
    confidence: float
    units: list[dict]
    self_contained_assessment: dict
    layout_concerns: list[str]
    suitable_for_title_split: bool
    analysis_notes: str
    analyzed_at: str


@router.get("/{property_id}", response_model=PropertyDetail)
async def get_property_detail(property_id: UUID):
    """Get full property details including manual inputs."""
    try:
        async with AsyncSessionLocal() as session:
            # First try without manual_inputs to debug
            result = await session.execute(
                select(Property)
                .where(Property.id == property_id)
            )
            property = result.scalar_one_or_none()

            if not property:
                raise HTTPException(status_code=404, detail="Property not found")

            # Try to load manual inputs separately with error handling
            manual_input = None
            try:
                mi_result = await session.execute(
                    select(ManualInput)
                    .where(ManualInput.property_id == property_id)
                    .limit(1)
                )
                manual_input = mi_result.scalar_one_or_none()
            except Exception as mi_err:
                logger.warning("Failed to load manual inputs", error=str(mi_err))
                # Continue without manual inputs

            return PropertyDetail(
                id=str(property.id),
                source_url=property.source_url,
                title=property.title,
                asking_price=property.asking_price,
                city=property.city or "",
                postcode=property.postcode or "",
                estimated_units=property.estimated_units,
                tenure=property.tenure,
                tenure_confidence=property.tenure_confidence,
                opportunity_score=property.opportunity_score,
                status=property.status,
                first_seen=property.first_seen.isoformat() if property.first_seen else "",
                manual_inputs=_serialize_manual_input(manual_input) if manual_input else None,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in get_property_detail", property_id=str(property_id), error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=f"Database error: {type(e).__name__}: {str(e)}")


@router.put("/{property_id}/manual", response_model=RecalculatedAnalysis)
async def update_manual_input(property_id: UUID, data: ManualInputUpdate):
    """
    Update manual verification data and recalculate analysis.

    Each manual input can:
    - Block the deal (e.g., leasehold tenure)
    - Add warnings (e.g., planning constraints)
    - Improve confidence (e.g., verified units)
    - Adjust costs (e.g., additional works needed)
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Property)
            .options(selectinload(Property.manual_inputs))
            .where(Property.id == property_id)
        )
        property = result.scalar_one_or_none()

        if not property:
            raise HTTPException(status_code=404, detail="Property not found")

        # Get or create manual input record
        if property.manual_inputs:
            manual_input = property.manual_inputs[0]
        else:
            manual_input = ManualInput(property_id=property_id)
            session.add(manual_input)

        # Update fields from request
        update_data = data.model_dump(exclude_unset=True)

        # Handle Property model fields separately
        if "postcode" in update_data:
            property.postcode = update_data.pop("postcode")
        if "city" in update_data:
            property.city = update_data.pop("city")

        # Update ManualInput fields
        for field, value in update_data.items():
            if hasattr(manual_input, field):
                setattr(manual_input, field, value)

        # Set verification timestamps
        if data.verified_tenure:
            manual_input.title_verified_date = datetime.utcnow()
        if data.verified_units:
            manual_input.units_verified_date = datetime.utcnow()
        if data.site_visited:
            manual_input.site_visit_date = datetime.utcnow()

        await session.commit()
        await session.refresh(manual_input)
        await session.refresh(property)  # Refresh property to ensure postcode/city are persisted

        # Calculate impact and update recommendation
        analysis = await _calculate_impact(property, manual_input)

        # Update property score based on analysis
        property.opportunity_score = analysis.adjusted_score
        property.status = "blocked" if analysis.blockers else "analysed"
        await session.commit()

        return analysis


@router.post("/{property_id}/recalculate", response_model=RecalculatedAnalysis)
async def recalculate_analysis(property_id: UUID):
    """Recalculate analysis with current data and manual inputs."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Property)
            .options(selectinload(Property.manual_inputs))
            .where(Property.id == property_id)
        )
        property = result.scalar_one_or_none()

        if not property:
            raise HTTPException(status_code=404, detail="Property not found")

        manual_input = property.manual_inputs[0] if property.manual_inputs else None
        analysis = await _calculate_impact(property, manual_input)

        # Update property
        property.opportunity_score = analysis.adjusted_score
        await session.commit()

        return analysis


async def _calculate_impact(property: Property, manual_input: Optional[ManualInput]) -> RecalculatedAnalysis:
    """
    Calculate the impact of manual inputs on the deal analysis.

    Impact rules:
    - Leasehold tenure: BLOCKER (-100 points)
    - Unknown tenure with no verification: -20 points
    - Verified freehold: +15 points
    - Single title confirmed: +10 points
    - Planning constraints (conservation/listed): WARNING (-15 points)
    - Article 4 direction: WARNING (-10 points)
    - HMO license required but not licensed: WARNING (-10 points)
    - Site visited with good condition: +10 points
    - Site visited with poor condition: -20 points
    - Structural concerns: BLOCKER
    """
    impacts = []
    blockers = []
    warnings = []
    positives = []
    score_adjustment = 0
    original_score = property.opportunity_score

    # Determine effective values (manual overrides scraped)
    effective_units = property.estimated_units
    effective_tenure = property.tenure
    effective_price = property.asking_price

    if manual_input:
        if manual_input.verified_units:
            effective_units = manual_input.verified_units
            impacts.append(ImpactItem(
                field="verified_units",
                impact_type="positive",
                score_adjustment=5,
                message=f"Units verified: {effective_units}"
            ))
            score_adjustment += 5
            positives.append(f"Verified {effective_units} units")

        if manual_input.verified_tenure:
            effective_tenure = manual_input.verified_tenure
            if effective_tenure == "leasehold":
                impacts.append(ImpactItem(
                    field="verified_tenure",
                    impact_type="blocker",
                    score_adjustment=-100,
                    message="BLOCKER: Property is leasehold - title split not viable"
                ))
                blockers.append({"type": "tenure", "reason": "Leasehold property cannot be title split"})
                score_adjustment -= 100
            elif effective_tenure == "freehold":
                impacts.append(ImpactItem(
                    field="verified_tenure",
                    impact_type="positive",
                    score_adjustment=15,
                    message="Freehold tenure verified - suitable for title split"
                ))
                score_adjustment += 15
                positives.append("Freehold tenure verified")

        if manual_input.is_single_title is not None:
            if manual_input.is_single_title:
                impacts.append(ImpactItem(
                    field="is_single_title",
                    impact_type="positive",
                    score_adjustment=10,
                    message="Single title confirmed - straightforward split"
                ))
                score_adjustment += 10
                positives.append("Single title confirmed")
            else:
                impacts.append(ImpactItem(
                    field="is_single_title",
                    impact_type="warning",
                    score_adjustment=-10,
                    message="Multiple titles may complicate the split"
                ))
                score_adjustment -= 10
                warnings.append("Multiple titles - may complicate split")

        if manual_input.planning_checked:
            constraints = manual_input.planning_constraints or {}
            if constraints.get("conservation_area"):
                impacts.append(ImpactItem(
                    field="planning_constraints",
                    impact_type="warning",
                    score_adjustment=-15,
                    message="Conservation area - additional planning considerations"
                ))
                score_adjustment -= 15
                warnings.append("Conservation area restrictions")
            if constraints.get("listed_building"):
                impacts.append(ImpactItem(
                    field="planning_constraints",
                    impact_type="blocker",
                    score_adjustment=-50,
                    message="Listed building - significant restrictions on works"
                ))
                blockers.append({"type": "planning", "reason": "Listed building restrictions"})
                score_adjustment -= 50
            if constraints.get("article_4"):
                impacts.append(ImpactItem(
                    field="planning_constraints",
                    impact_type="warning",
                    score_adjustment=-10,
                    message="Article 4 direction - may require planning permission"
                ))
                score_adjustment -= 10
                warnings.append("Article 4 direction applies")
            if not constraints:
                impacts.append(ImpactItem(
                    field="planning_checked",
                    impact_type="positive",
                    score_adjustment=5,
                    message="Planning checked - no constraints identified"
                ))
                score_adjustment += 5
                positives.append("No planning constraints")

        if manual_input.hmo_license_required:
            if manual_input.hmo_license_status == "licensed":
                positives.append("HMO license in place")
            elif manual_input.hmo_license_status in ["pending", "unknown"]:
                impacts.append(ImpactItem(
                    field="hmo_license_status",
                    impact_type="warning",
                    score_adjustment=-10,
                    message="HMO license required but not confirmed"
                ))
                score_adjustment -= 10
                warnings.append("HMO license status unclear")

        if manual_input.site_visited:
            if manual_input.condition_rating == "excellent":
                score_adjustment += 15
                positives.append("Excellent condition verified on site")
            elif manual_input.condition_rating == "good":
                score_adjustment += 10
                positives.append("Good condition verified on site")
            elif manual_input.condition_rating == "fair":
                score_adjustment += 0
                warnings.append("Fair condition - budget for some works")
            elif manual_input.condition_rating == "poor":
                score_adjustment -= 20
                warnings.append("Poor condition - significant works required")

            if manual_input.structural_concerns:
                impacts.append(ImpactItem(
                    field="structural_concerns",
                    impact_type="blocker",
                    score_adjustment=-50,
                    message=f"Structural concerns: {manual_input.structural_concerns}"
                ))
                blockers.append({"type": "structural", "reason": manual_input.structural_concerns})
                score_adjustment -= 50

        if manual_input.revised_asking_price:
            effective_price = manual_input.revised_asking_price

        if manual_input.blockers:
            for blocker in manual_input.blockers:
                blockers.append(blocker)

    # If tenure still unknown, penalize
    if effective_tenure == "unknown" and not (manual_input and manual_input.verified_tenure):
        impacts.append(ImpactItem(
            field="tenure",
            impact_type="warning",
            score_adjustment=-20,
            message="Tenure unverified - must confirm freehold before proceeding"
        ))
        score_adjustment -= 20
        warnings.append("Tenure not verified")

    # Calculate costs
    cost_breakdown = _calculate_costs(effective_units, effective_price, manual_input)

    # Get valuation if we have postcode and units
    valuation = None
    if property.postcode and effective_units > 0:
        try:
            valuation = await calculate_title_split_potential(
                postcode=property.postcode,
                asking_price=effective_price,
                num_units=effective_units,
            )
        except Exception as e:
            logger.warning("Valuation failed during recalc", error=str(e))

    # Calculate net benefit
    if valuation and valuation.get("status") == "success":
        net_benefit_per_unit = valuation.get("net_per_unit", 0)
    else:
        # Fallback calculation
        avg_unit_value = effective_price // effective_units if effective_units > 0 else 0
        gross_uplift = (avg_unit_value * 1.3 * effective_units) - effective_price  # Assume 30% uplift
        net_benefit_per_unit = int((gross_uplift - cost_breakdown["total"]) // effective_units) if effective_units > 0 else 0

    # Determine final score and recommendation
    adjusted_score = max(0, min(100, original_score + score_adjustment))

    if blockers:
        recommendation = "decline"
        confidence = "high"
    elif adjusted_score >= 70 and net_benefit_per_unit >= 5000:
        recommendation = "proceed"
        confidence = "high" if manual_input and manual_input.verified_tenure else "medium"
    elif adjusted_score >= 50 and net_benefit_per_unit >= 2000:
        recommendation = "review"
        confidence = "medium"
    else:
        recommendation = "decline"
        confidence = "medium"

    # Original recommendation based on score alone
    original_recommendation = "proceed" if original_score >= 70 else "review" if original_score >= 50 else "decline"

    return RecalculatedAnalysis(
        property_id=str(property.id),
        original_score=original_score,
        adjusted_score=adjusted_score,
        original_recommendation=original_recommendation,
        updated_recommendation=recommendation,
        impacts=impacts,
        confidence_level=confidence,
        valuation=valuation,
        cost_breakdown=cost_breakdown,
        net_benefit_per_unit=net_benefit_per_unit,
        blockers=blockers,
        warnings=warnings,
        positives=positives,
    )


def _calculate_costs(num_units: int, asking_price: int, manual_input: Optional[ManualInput]) -> dict:
    """
    Calculate detailed cost breakdown for title split.

    Cost components:
    - Land Registry fees (banded by value)
    - Legal fees (~£1,000 per unit)
    - Survey/valuation (~£500 per unit)
    - Lease extension (if needed, ~£5,000 per unit)
    - Additional costs from manual input
    """
    # Land Registry fee bands (per unit)
    unit_value_estimate = asking_price // num_units if num_units > 0 else asking_price
    if unit_value_estimate <= 80000:
        lr_fee = 20
    elif unit_value_estimate <= 100000:
        lr_fee = 40
    elif unit_value_estimate <= 200000:
        lr_fee = 95
    elif unit_value_estimate <= 500000:
        lr_fee = 135
    elif unit_value_estimate <= 1000000:
        lr_fee = 270
    else:
        lr_fee = 455

    legal_per_unit = 1000
    survey_per_unit = 500
    admin_per_unit = 200

    base_cost_per_unit = lr_fee + legal_per_unit + survey_per_unit + admin_per_unit

    # Additional costs from manual input
    additional = 0
    additional_items = {}
    if manual_input and manual_input.additional_costs_identified:
        for item, cost in manual_input.additional_costs_identified.items():
            additional += cost
            additional_items[item] = cost

    total = (base_cost_per_unit * num_units) + additional

    return {
        "land_registry_per_unit": lr_fee,
        "legal_per_unit": legal_per_unit,
        "survey_per_unit": survey_per_unit,
        "admin_per_unit": admin_per_unit,
        "base_per_unit": base_cost_per_unit,
        "num_units": num_units,
        "base_total": base_cost_per_unit * num_units,
        "additional_costs": additional_items,
        "additional_total": additional,
        "total": total,
    }


def _serialize_manual_input(mi: ManualInput) -> dict:
    """Serialize ManualInput to dict."""
    return {
        "verified_tenure": mi.verified_tenure,
        "title_number": mi.title_number,
        "is_single_title": mi.is_single_title,
        "title_verified_date": mi.title_verified_date.isoformat() if mi.title_verified_date else None,
        "title_notes": mi.title_notes,
        "verified_units": mi.verified_units,
        "unit_breakdown": mi.unit_breakdown,
        "units_verified_date": mi.units_verified_date.isoformat() if mi.units_verified_date else None,
        "planning_checked": mi.planning_checked,
        "planning_constraints": mi.planning_constraints,
        "planning_notes": mi.planning_notes,
        "hmo_license_required": mi.hmo_license_required,
        "hmo_license_status": mi.hmo_license_status,
        "site_visited": mi.site_visited,
        "site_visit_date": mi.site_visit_date.isoformat() if mi.site_visit_date else None,
        "condition_rating": mi.condition_rating,
        "access_issues": mi.access_issues,
        "structural_concerns": mi.structural_concerns,
        "floorplan_filename": mi.floorplan_filename,
        "floorplan_analysis": mi.floorplan_analysis,
        "floorplan_analyzed_at": mi.floorplan_analyzed_at.isoformat() if mi.floorplan_analyzed_at else None,
        "revised_asking_price": mi.revised_asking_price,
        "additional_costs_identified": mi.additional_costs_identified,
        "negotiation_notes": mi.negotiation_notes,
        "deal_status": mi.deal_status,
        "blockers": mi.blockers,
        "updated_at": mi.updated_at.isoformat() if mi.updated_at else None,
    }


# ============================================================
# GDV Report Generation
# ============================================================

class UnitInput(BaseModel):
    """Single unit specification for GDV calculation."""
    id: str = Field(description="Unit identifier, e.g., 'Flat 1'")
    beds: Optional[int] = Field(None, description="Number of bedrooms")
    sqft: Optional[float] = Field(None, description="Floor area in square feet")
    epc: Optional[str] = Field(None, description="EPC rating A-G")


class GDVReportRequest(BaseModel):
    """Request for generating a lender-grade GDV report."""
    units: Optional[list[UnitInput]] = Field(
        None,
        description="Unit breakdown. If not provided, will auto-generate from estimated_units"
    )
    refurbishment_budget: Optional[int] = Field(None, description="Additional refurb costs")
    title_number: Optional[str] = Field(None, description="Land Registry title number")


class GDVReportResponse(BaseModel):
    """Lender-grade GDV report response."""
    property_address: str
    postcode: str
    title_number: Optional[str] = None
    asking_price: int
    total_units: int
    total_sqft: Optional[float] = None

    # Unit valuations
    unit_valuations: list[dict]

    # GDV summary
    total_gdv: int
    gdv_range_low: int
    gdv_range_high: int
    gdv_confidence: str

    # Uplift analysis
    gross_uplift: int
    gross_uplift_percent: float
    title_split_costs: int
    refurbishment_budget: Optional[int] = None
    total_costs: int
    net_uplift: int
    net_uplift_percent: float
    net_profit_per_unit: int

    # Market context
    local_market_data: dict
    comparables_summary: dict

    # Report metadata
    data_sources: list[str]
    data_freshness: str
    confidence_statement: str
    limitations: list[str]
    report_date: str


@router.post("/{property_id}/gdv-report", response_model=GDVReportResponse)
async def generate_gdv_report(property_id: UUID, request: GDVReportRequest):
    """
    Generate a lender-grade GDV report for a property.

    This endpoint produces a comprehensive valuation report suitable
    for presenting to bridge/development lenders, including:

    - Unit-by-unit valuations with confidence levels
    - Land Registry comparable evidence
    - EPC-derived floor area data
    - Market context (HPI, yields, growth)
    - Professional confidence statement
    - Limitations and caveats

    Data sources:
    - HM Land Registry Price Paid Data (verified transactions)
    - PropertyData.co.uk (AVM, £/sqft analysis)
    - UK House Price Index (time adjustments)
    - EPC Register (floor areas, energy ratings)
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Property)
            .options(selectinload(Property.manual_inputs))
            .where(Property.id == property_id)
        )
        property = result.scalar_one_or_none()

        if not property:
            raise HTTPException(status_code=404, detail="Property not found")

        if not property.postcode:
            raise HTTPException(status_code=400, detail="Property postcode required for GDV report")

        # Get effective values (prefer manual inputs)
        manual_input = property.manual_inputs[0] if property.manual_inputs else None
        effective_units = (
            manual_input.verified_units if manual_input and manual_input.verified_units
            else property.estimated_units
        )
        effective_price = (
            manual_input.revised_asking_price if manual_input and manual_input.revised_asking_price
            else property.asking_price
        )

        if effective_units <= 0:
            raise HTTPException(status_code=400, detail="Property must have at least 1 unit")

        # Build unit list
        if request.units:
            units = [u.model_dump() for u in request.units]
        elif manual_input and manual_input.unit_breakdown:
            units = manual_input.unit_breakdown
        else:
            # Auto-generate unit list
            units = [{"id": f"Unit {i+1}", "beds": 2} for i in range(effective_units)]

        # Initialize clients
        lr_client = LandRegistryClient()
        epc_client = EPCClient()

        # Get comparables
        logger.info("Fetching Land Registry comparables", postcode=property.postcode)
        comparables = await lr_client.get_comparable_sales(
            postcode=property.postcode,
            property_type="F",  # Flats
            months_back=18,
        )

        # Get EPC data if available
        logger.info("Fetching EPC records", postcode=property.postcode)
        epcs = await epc_client.search_by_postcode(property.postcode)

        # Initialize calculator and generate report
        calculator = GDVCalculator(
            land_registry_client=lr_client,
        )

        logger.info("Calculating GDV", units=len(units), asking_price=effective_price)
        report = await calculator.calculate_block_gdv(
            postcode=property.postcode,
            units=units,
            asking_price=effective_price,
            comparables=comparables,
            epcs=epcs,
            split_costs=request.refurbishment_budget or 0,
        )

        # Build response
        return GDVReportResponse(
            property_address=property.title or property.address_line1 or "",
            postcode=property.postcode,
            title_number=request.title_number or (manual_input.title_number if manual_input else None),
            asking_price=effective_price,
            total_units=report.total_units,
            total_sqft=report.total_sqft,
            unit_valuations=[_serialize_unit_valuation(uv) for uv in report.unit_valuations],
            total_gdv=report.total_gdv,
            gdv_range_low=report.gdv_range_low,
            gdv_range_high=report.gdv_range_high,
            gdv_confidence=report.gdv_confidence.value,
            gross_uplift=report.gross_uplift,
            gross_uplift_percent=report.gross_uplift_percent,
            title_split_costs=report.title_split_costs,
            refurbishment_budget=request.refurbishment_budget,
            total_costs=report.total_costs + _calculate_costs(report.total_units, effective_price, manual_input)["total"],
            net_uplift=report.net_uplift,
            net_uplift_percent=report.net_uplift_percent,
            net_profit_per_unit=report.net_profit_per_unit,
            local_market_data=report.local_market_data,
            comparables_summary=report.comparables_summary,
            data_sources=report.data_sources,
            data_freshness=report.data_freshness,
            confidence_statement=report.confidence_statement,
            limitations=report.limitations,
            report_date=report.report_date,
        )


def _serialize_unit_valuation(uv: UnitValuation) -> dict:
    """Serialize UnitValuation for API response."""
    return {
        "unit_identifier": uv.unit_identifier,
        "beds": uv.beds,
        "sqft": uv.sqft,
        "epc_rating": uv.epc_rating,
        "estimated_value": uv.estimated_value,
        "value_range_low": uv.value_range_low,
        "value_range_high": uv.value_range_high,
        "confidence": uv.confidence.value,
        "primary_method": uv.primary_method,
        "price_per_sqft_used": uv.price_per_sqft_used,
        "valuation_notes": uv.valuation_notes,
    }


# ============================================================
# Archive/Restore Endpoints
# ============================================================

@router.post("/{property_id}/archive")
async def archive_property(property_id: UUID):
    """Archive a property (soft delete)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Property).where(Property.id == property_id)
        )
        property = result.scalar_one_or_none()

        if not property:
            raise HTTPException(status_code=404, detail="Property not found")

        property.archived = True
        await session.commit()

        return {"status": "archived", "property_id": str(property_id)}


@router.post("/{property_id}/restore")
async def restore_property(property_id: UUID):
    """Restore an archived property."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Property).where(Property.id == property_id)
        )
        property = result.scalar_one_or_none()

        if not property:
            raise HTTPException(status_code=404, detail="Property not found")

        property.archived = False
        await session.commit()

        return {"status": "restored", "property_id": str(property_id)}


@router.delete("/{property_id}")
async def delete_property(property_id: UUID, permanent: bool = False):
    """
    Delete a property.

    By default, performs soft delete (archive).
    Use permanent=true for hard delete.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Property).where(Property.id == property_id)
        )
        property = result.scalar_one_or_none()

        if not property:
            raise HTTPException(status_code=404, detail="Property not found")

        if permanent:
            await session.delete(property)
            await session.commit()
            return {"status": "deleted", "property_id": str(property_id)}
        else:
            property.archived = True
            await session.commit()
            return {"status": "archived", "property_id": str(property_id)}


# ============================================================
# Floorplan Upload & Analysis
# ============================================================

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


@router.post("/{property_id}/floorplan", response_model=FloorplanAnalysisResponse)
async def analyze_floorplan(property_id: UUID, file: UploadFile = File(...)):
    """
    Upload and analyze a floorplan image using Claude Vision.

    Accepts: JPEG, PNG, WebP, GIF (max 5MB)

    Returns room counts and layout analysis:
    - Number of units detected
    - Room breakdown per unit (beds, baths, reception)
    - Self-containment assessment
    - Suitability for title split
    """
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"
        )

    # Read and validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Property)
            .options(selectinload(Property.manual_inputs))
            .where(Property.id == property_id)
        )
        property = result.scalar_one_or_none()

        if not property:
            raise HTTPException(status_code=404, detail="Property not found")

        # Get or create manual input record
        if property.manual_inputs:
            manual_input = property.manual_inputs[0]
        else:
            manual_input = ManualInput(property_id=property_id)
            session.add(manual_input)

        # Convert to base64
        image_base64 = base64.b64encode(content).decode("utf-8")

        # Analyze with Claude Vision
        logger.info("Analyzing floorplan", property_id=str(property_id), filename=file.filename)
        analyzer = FloorplanAnalyzer()

        try:
            analysis = await analyzer.analyze(image_base64, file.content_type)
        except Exception as e:
            logger.error("Floorplan analysis failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

        # Store results
        manual_input.floorplan_base64 = image_base64
        manual_input.floorplan_filename = file.filename
        manual_input.floorplan_analysis = analyzer.analysis_to_dict(analysis)
        manual_input.floorplan_analyzed_at = analysis.analyzed_at

        await session.commit()

        logger.info(
            "Floorplan analysis complete",
            property_id=str(property_id),
            units_detected=analysis.units_detected
        )

        return FloorplanAnalysisResponse(
            units_detected=analysis.units_detected,
            confidence=analysis.confidence,
            units=[
                {
                    "unit_id": u.unit_id,
                    "layout_type": u.layout_type,
                    "bedrooms": u.bedrooms,
                    "bathrooms": u.bathrooms,
                    "reception_rooms": u.reception_rooms,
                    "has_kitchen": u.has_kitchen,
                    "estimated_sqft": u.estimated_sqft,
                    "notes": u.notes,
                }
                for u in analysis.units
            ],
            self_contained_assessment={
                "all_self_contained": analysis.self_contained_assessment.all_self_contained,
                "concerns": analysis.self_contained_assessment.concerns,
                "evidence": analysis.self_contained_assessment.evidence,
            },
            layout_concerns=analysis.layout_concerns,
            suitable_for_title_split=analysis.suitable_for_title_split,
            analysis_notes=analysis.analysis_notes,
            analyzed_at=analysis.analyzed_at.isoformat(),
        )

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.property import Property
from src.models.manual_inputs import (
    ManualInputs,
    TitleInputs,
    TitleVerification,
    ExistingCharge,
    RestrictiveCovenant,
    Easement,
    PlanningInputs,
    PlanningStatus,
    HMOLicensing,
    PhysicalVerification,
    UnitVerification,
    FinancialVerification,
)
from src.analysis.impact_rules import (
    TENURE_IMPACTS,
    SINGLE_TITLE_IMPACTS,
    TITLE_CLASS_IMPACTS,
    USE_CLASS_IMPACTS,
    assess_charge_impact,
    assess_covenant_impact,
    assess_hmo_licensing_impact,
    assess_physical_impact,
    calculate_total_impact,
    Impact,
)
from src.analysis.recommendation import (
    generate_verified_recommendation,
    Recommendation,
)

router = APIRouter(prefix="/properties/{property_id}/manual", tags=["manual-inputs"])


# In-memory storage for manual inputs (replace with database in production)
_manual_inputs_store: dict[str, ManualInputs] = {}


@router.get("", response_model=ManualInputs)
async def get_manual_inputs(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get all manual inputs for a property."""
    # Verify property exists
    result = await db.execute(select(Property).where(Property.id == property_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Property not found")

    key = str(property_id)
    if key not in _manual_inputs_store:
        _manual_inputs_store[key] = ManualInputs(property_id=key)

    return _manual_inputs_store[key]


@router.put("/title/verification", response_model=dict)
async def update_title_verification(
    property_id: UUID,
    verification: TitleVerification,
    db: AsyncSession = Depends(get_db),
):
    """Update title verification data."""
    key = str(property_id)
    if key not in _manual_inputs_store:
        _manual_inputs_store[key] = ManualInputs(property_id=key)

    inputs = _manual_inputs_store[key]
    inputs.title.verification = verification
    inputs.last_updated = date.today()

    # Calculate impacts
    impacts = []
    if verification.tenure_confirmed:
        impact = TENURE_IMPACTS.get(verification.tenure_confirmed)
        if impact:
            impacts.append(impact)

    if verification.is_single_title is not None:
        impact = SINGLE_TITLE_IMPACTS.get(verification.is_single_title)
        if impact:
            impacts.append(impact)

    if verification.title_class:
        impact = TITLE_CLASS_IMPACTS.get(verification.title_class)
        if impact:
            impacts.append(impact)

    impact_summary = calculate_total_impact(impacts)

    return {
        "status": "updated",
        "impacts": [i.model_dump() for i in impacts],
        "impact_summary": impact_summary,
    }


@router.post("/title/charges", response_model=dict)
async def add_existing_charge(
    property_id: UUID,
    charge: ExistingCharge,
    db: AsyncSession = Depends(get_db),
):
    """Add an existing charge to the property."""
    key = str(property_id)
    if key not in _manual_inputs_store:
        _manual_inputs_store[key] = ManualInputs(property_id=key)

    inputs = _manual_inputs_store[key]
    inputs.title.charges.append(charge)
    inputs.last_updated = date.today()

    # Calculate impact
    impact = assess_charge_impact(charge)

    return {
        "status": "added",
        "impact": impact.model_dump(),
    }


@router.post("/title/covenants", response_model=dict)
async def add_covenant(
    property_id: UUID,
    covenant: RestrictiveCovenant,
    db: AsyncSession = Depends(get_db),
):
    """Add a restrictive covenant."""
    key = str(property_id)
    if key not in _manual_inputs_store:
        _manual_inputs_store[key] = ManualInputs(property_id=key)

    inputs = _manual_inputs_store[key]
    inputs.title.covenants.append(covenant)
    inputs.last_updated = date.today()

    impact = assess_covenant_impact(covenant)

    return {
        "status": "added",
        "impact": impact.model_dump(),
    }


@router.put("/planning/status", response_model=dict)
async def update_planning_status(
    property_id: UUID,
    status: PlanningStatus,
    db: AsyncSession = Depends(get_db),
):
    """Update planning status."""
    key = str(property_id)
    if key not in _manual_inputs_store:
        _manual_inputs_store[key] = ManualInputs(property_id=key)

    inputs = _manual_inputs_store[key]
    inputs.planning.planning_status = status
    inputs.last_updated = date.today()

    impacts = []
    if status.current_use_class:
        impact = USE_CLASS_IMPACTS.get(status.current_use_class)
        if impact:
            impacts.append(impact)

    impact_summary = calculate_total_impact(impacts)

    return {
        "status": "updated",
        "impacts": [i.model_dump() for i in impacts],
        "impact_summary": impact_summary,
    }


@router.put("/planning/hmo", response_model=dict)
async def update_hmo_licensing(
    property_id: UUID,
    hmo: HMOLicensing,
    db: AsyncSession = Depends(get_db),
):
    """Update HMO licensing status."""
    key = str(property_id)
    if key not in _manual_inputs_store:
        _manual_inputs_store[key] = ManualInputs(property_id=key)

    inputs = _manual_inputs_store[key]
    inputs.planning.hmo_licensing = hmo
    inputs.last_updated = date.today()

    impacts = assess_hmo_licensing_impact(hmo)
    impact_summary = calculate_total_impact(impacts)

    return {
        "status": "updated",
        "impacts": [i.model_dump() for i in impacts],
        "impact_summary": impact_summary,
    }


@router.put("/physical", response_model=dict)
async def update_physical_verification(
    property_id: UUID,
    physical: PhysicalVerification,
    db: AsyncSession = Depends(get_db),
):
    """Update physical verification data."""
    key = str(property_id)
    if key not in _manual_inputs_store:
        _manual_inputs_store[key] = ManualInputs(property_id=key)

    inputs = _manual_inputs_store[key]
    inputs.physical = physical
    inputs.last_updated = date.today()

    impacts = assess_physical_impact(physical)
    impact_summary = calculate_total_impact(impacts)

    return {
        "status": "updated",
        "impacts": [i.model_dump() for i in impacts],
        "impact_summary": impact_summary,
    }


@router.put("/financial", response_model=dict)
async def update_financial_verification(
    property_id: UUID,
    financial: FinancialVerification,
    db: AsyncSession = Depends(get_db),
):
    """Update financial verification data."""
    key = str(property_id)
    if key not in _manual_inputs_store:
        _manual_inputs_store[key] = ManualInputs(property_id=key)

    inputs = _manual_inputs_store[key]
    inputs.financial = financial
    inputs.last_updated = date.today()

    return {"status": "updated"}


@router.get("/recommendation", response_model=Recommendation)
async def get_updated_recommendation(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get updated recommendation based on manual inputs."""
    # Get property
    result = await db.execute(select(Property).where(Property.id == property_id))
    property = result.scalar_one_or_none()
    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    key = str(property_id)
    inputs = _manual_inputs_store.get(key, ManualInputs(property_id=key))

    # Calculate estimated net benefit
    estimated_net_benefit = property.estimated_net_uplift

    # Generate recommendation
    recommendation = generate_verified_recommendation(
        property=property,
        manual_inputs=inputs,
        estimated_net_benefit=estimated_net_benefit,
    )

    return recommendation


@router.get("/completion", response_model=dict)
async def get_completion_status(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get completion percentage for manual inputs."""
    key = str(property_id)
    inputs = _manual_inputs_store.get(key, ManualInputs(property_id=key))

    # Calculate completion
    total_items = 10
    completed = 0

    if inputs.title.verification:
        if inputs.title.verification.tenure_confirmed:
            completed += 1
        if inputs.title.verification.is_single_title is not None:
            completed += 1
        if inputs.title.verification.title_number:
            completed += 1

    if inputs.planning.planning_status:
        if inputs.planning.planning_status.current_use_class:
            completed += 1
        if inputs.planning.planning_status.original_conversion_consented is not None:
            completed += 1

    if inputs.planning.hmo_licensing:
        completed += 1

    if inputs.physical:
        if inputs.physical.units:
            completed += 1
        if inputs.physical.viewing_date:
            completed += 1

    if inputs.financial:
        completed += 1

    completion_pct = round((completed / total_items) * 100, 1)
    inputs.completion_percentage = completion_pct

    return {
        "completion_percentage": completion_pct,
        "items_completed": completed,
        "items_total": total_items,
        "missing_critical": _get_missing_critical(inputs),
    }


def _get_missing_critical(inputs: ManualInputs) -> list[str]:
    """Get list of missing critical items."""
    missing = []

    if not inputs.title.verification or not inputs.title.verification.tenure_confirmed:
        missing.append("Tenure verification")

    if not inputs.title.verification or inputs.title.verification.is_single_title is None:
        missing.append("Single title confirmation")

    if not inputs.planning.planning_status or not inputs.planning.planning_status.current_use_class:
        missing.append("Use class verification")

    if not inputs.physical or not inputs.physical.units:
        missing.append("Physical inspection")

    return missing

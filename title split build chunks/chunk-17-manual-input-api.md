## CHUNK 17: API Endpoints for Manual Inputs

### 17.1 Manual Input API

```python
# src/api/manual_inputs.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ..database import get_db
from ..models.manual_inputs import (
    ManualInputs, TitleVerification, ExistingCharge, 
    RestrictiveCovenant, PlanningStatus, HMOLicensing,
    PhysicalVerification, UnitVerification
)
from ..analysis.recommendation_engine import RecommendationEngine
from ..analysis.impact_rules import Impact

router = APIRouter(prefix="/properties/{property_id}/manual", tags=["manual-inputs"])


@router.get("/", response_model=ManualInputs)
async def get_manual_inputs(
    property_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all manual inputs for a property."""
    # Load from database
    pass


@router.put("/title/verification", response_model=dict)
async def update_title_verification(
    property_id: UUID,
    verification: TitleVerification,
    db: AsyncSession = Depends(get_db)
):
    """
    Update title verification details.
    
    Returns: Updated recommendation and specific impacts.
    """
    # Load property and existing inputs
    property = await get_property(property_id, db)
    inputs = await get_or_create_manual_inputs(property_id, db)
    
    # Update title verification
    inputs.title.verification = verification
    
    # Calculate impacts
    engine = RecommendationEngine(property, inputs)
    impacts = engine.calculate_all_impacts()
    recommendation = engine.generate_updated_recommendation()
    
    # Save and return
    await save_manual_inputs(inputs, db)
    
    return {
        "impacts": [i.dict() for i in impacts if i.input_field.startswith("tenure") or i.input_field.startswith("title") or i.input_field == "is_single_title"],
        "recommendation": recommendation.dict(),
        "message": "Title verification updated"
    }


@router.post("/title/charges", response_model=dict)
async def add_charge(
    property_id: UUID,
    charge: ExistingCharge,
    db: AsyncSession = Depends(get_db)
):
    """
    Add an existing charge to the title inputs.
    
    Returns: Impact assessment for this specific charge.
    """
    property = await get_property(property_id, db)
    inputs = await get_or_create_manual_inputs(property_id, db)
    
    # Add charge
    inputs.title.charges.append(charge)
    
    # Calculate impact for this charge
    from ..analysis.impact_rules import assess_charge_impact
    impact = assess_charge_impact(charge)
    
    # Recalculate full recommendation
    engine = RecommendationEngine(property, inputs)
    recommendation = engine.generate_updated_recommendation()
    
    await save_manual_inputs(inputs, db)
    
    return {
        "impact": impact.dict(),
        "recommendation": recommendation.dict(),
        "message": f"Charge from {charge.lender_name} added"
    }


@router.post("/title/covenants", response_model=dict)
async def add_covenant(
    property_id: UUID,
    covenant: RestrictiveCovenant,
    db: AsyncSession = Depends(get_db)
):
    """
    Add a restrictive covenant to the title inputs.
    
    Returns: Impact assessment for this covenant.
    """
    property = await get_property(property_id, db)
    inputs = await get_or_create_manual_inputs(property_id, db)
    
    inputs.title.covenants.append(covenant)
    
    from ..analysis.impact_rules import assess_covenant_impact
    impact = assess_covenant_impact(covenant)
    
    engine = RecommendationEngine(property, inputs)
    recommendation = engine.generate_updated_recommendation()
    
    await save_manual_inputs(inputs, db)
    
    return {
        "impact": impact.dict(),
        "recommendation": recommendation.dict(),
        "message": "Covenant added"
    }


@router.put("/planning/status", response_model=dict)
async def update_planning_status(
    property_id: UUID,
    planning: PlanningStatus,
    db: AsyncSession = Depends(get_db)
):
    """
    Update planning verification status.
    
    Returns: Planning-related impacts and updated recommendation.
    """
    property = await get_property(property_id, db)
    inputs = await get_or_create_manual_inputs(property_id, db)
    
    inputs.planning.planning_status = planning
    
    engine = RecommendationEngine(property, inputs)
    impacts = engine.calculate_all_impacts()
    recommendation = engine.generate_updated_recommendation()
    
    # Filter to planning impacts
    planning_impacts = [i for i in impacts if i.input_category == "planning"]
    
    await save_manual_inputs(inputs, db)
    
    return {
        "impacts": [i.dict() for i in planning_impacts],
        "recommendation": recommendation.dict(),
        "message": "Planning status updated"
    }


@router.put("/planning/hmo", response_model=dict)
async def update_hmo_licensing(
    property_id: UUID,
    hmo: HMOLicensing,
    db: AsyncSession = Depends(get_db)
):
    """
    Update HMO licensing status.
    
    Returns: HMO-related impacts and updated recommendation.
    """
    property = await get_property(property_id, db)
    inputs = await get_or_create_manual_inputs(property_id, db)
    
    inputs.planning.hmo_licensing = hmo
    
    from ..analysis.impact_rules import assess_hmo_licensing_impact
    hmo_impacts = assess_hmo_licensing_impact(hmo)
    
    engine = RecommendationEngine(property, inputs)
    recommendation = engine.generate_updated_recommendation()
    
    await save_manual_inputs(inputs, db)
    
    return {
        "impacts": [i.dict() for i in hmo_impacts],
        "recommendation": recommendation.dict(),
        "message": "HMO licensing status updated"
    }


@router.put("/physical", response_model=dict)
async def update_physical_verification(
    property_id: UUID,
    physical: PhysicalVerification,
    db: AsyncSession = Depends(get_db)
):
    """
    Update physical inspection findings.
    
    Returns: Physical-related impacts and updated recommendation.
    """
    property = await get_property(property_id, db)
    inputs = await get_or_create_manual_inputs(property_id, db)
    
    inputs.physical = physical
    
    from ..analysis.impact_rules import assess_physical_impact
    physical_impacts = assess_physical_impact(physical)
    
    engine = RecommendationEngine(property, inputs)
    recommendation = engine.generate_updated_recommendation()
    
    await save_manual_inputs(inputs, db)
    
    return {
        "impacts": [i.dict() for i in physical_impacts],
        "recommendation": recommendation.dict(),
        "message": "Physical verification updated"
    }


@router.get("/impacts", response_model=list[Impact])
async def get_all_impacts(
    property_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all impacts from manual inputs for this property.
    
    Useful for displaying a summary of all findings.
    """
    property = await get_property(property_id, db)
    inputs = await get_or_create_manual_inputs(property_id, db)
    
    engine = RecommendationEngine(property, inputs)
    impacts = engine.calculate_all_impacts()
    
    return impacts


@router.get("/checklist", response_model=dict)
async def get_verification_checklist(
    property_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a checklist of what's been verified and what's still needed.
    """
    inputs = await get_or_create_manual_inputs(property_id, db)
    
    checklist = {
        "title": {
            "tenure_verified": inputs.title.verification and inputs.title.verification.tenure_confirmed is not None,
            "single_title_verified": inputs.title.verification and inputs.title.verification.is_single_title is not None,
            "charges_checked": len(inputs.title.charges) > 0 or (inputs.title.verification and inputs.title.verification.notes and "no charges" in inputs.title.verification.notes.lower()),
            "covenants_checked": len(inputs.title.covenants) > 0 or (inputs.title.verification and inputs.title.verification.notes),
        },
        "planning": {
            "use_class_verified": inputs.planning.planning_status and inputs.planning.planning_status.use_class_verified,
            "conversion_verified": inputs.planning.planning_status and inputs.planning.planning_status.original_conversion_consented is not None,
            "building_regs_verified": inputs.planning.planning_status and inputs.planning.planning_status.building_regs_signed_off is not None,
            "hmo_status_verified": inputs.planning.hmo_licensing is not None,
        },
        "physical": {
            "inspection_completed": inputs.physical is not None,
            "units_verified": inputs.physical and len(inputs.physical.units) > 0,
            "self_containment_verified": inputs.physical and all(u.is_self_contained is not None for u in inputs.physical.units),
        },
        "completion_percentage": _calculate_completion(inputs),
    }
    
    return checklist


def _calculate_completion(inputs: ManualInputs) -> float:
    """Calculate percentage completion of manual verification."""
    
    total_items = 10
    completed = 0
    
    if inputs.title.verification:
        if inputs.title.verification.tenure_confirmed:
            completed += 1
        if inputs.title.verification.is_single_title is not None:
            completed += 1
    
    if inputs.title.charges or (inputs.title.verification and inputs.title.verification.notes):
        completed += 1
    
    if inputs.planning.planning_status:
        if inputs.planning.planning_status.use_class_verified:
            completed += 1
        if inputs.planning.planning_status.original_conversion_consented is not None:
            completed += 1
        if inputs.planning.planning_status.building_regs_signed_off is not None:
            completed += 1
    
    if inputs.planning.hmo_licensing:
        completed += 1
    
    if inputs.physical:
        completed += 1
        if inputs.physical.units:
            completed += 1
        if all(u.is_self_contained is not None for u in inputs.physical.units):
            completed += 1
    
    return (completed / total_items) * 100
```

---

## Summary: How Manual Inputs Affect the Deal

| Input Category | Example Input | Positive Impact | Negative Impact |
|---------------|---------------|-----------------|-----------------|
| **Title Verification** ||||
| Tenure | "Freehold" | +30 points, "Enabler" | "Leasehold" = BLOCKER |
| Single title | "Yes" | +20 points | "No" = BLOCKER |
| Title class | "Absolute" | +5 points | "Possessory" = -30, insurance needed |
| **Existing Charges** ||||
| Lender consent | "Likely" | -10 points, manageable | "Refused" = BLOCKER |
| All-monies charge | Present | -25 points, complex release | |
| **Covenants** ||||
| Use restriction | Not affecting split | Neutral | Affecting split = -25 |
| Alienation covenant | Not present | Neutral | Present = -35, may block disposals |
| **Planning** ||||
| Use class | C3 | +15 points | Sui generis = -25, complex |
| Conversion consent | Yes | +20 points | No = -40, CLEUD needed |
| Building regs | Signed off | +10 points | Not signed off = -30 |
| **HMO Licensing** ||||
| Mandatory licence | Held | Neutral | Not held = BLOCKER (criminal offence) |
| Fire safety | Compliant | Neutral | Non-compliant = -35, £5k works |
| **Physical** ||||
| Self-contained | All units | +25 points | Units not self-contained = -40 |
| Structural | No concerns | Neutral | Concerns = -50, survey needed |
| Boundaries | Clear | Neutral | Issues = -15, survey needed |

The system recalculates the recommendation after each manual input, showing exactly how it affects the deal viability and what actions are needed.
# Title Split Opportunity Finder


from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.models.manual_inputs import (
    TitleInputs,
    ExistingCharge,
    RestrictiveCovenant,
    PlanningInputs,
    HMOLicensing,
    PhysicalVerification,
)


class ImpactType(str, Enum):
    BLOCKER = "blocker"
    MAJOR_NEGATIVE = "major_neg"
    MINOR_NEGATIVE = "minor_neg"
    NEUTRAL = "neutral"
    MINOR_POSITIVE = "minor_pos"
    MAJOR_POSITIVE = "major_pos"
    ENABLER = "enabler"


class Impact(BaseModel):
    """Assessment of how a manual input impacts the deal."""

    input_category: str
    input_field: str
    input_value: str

    impact_type: ImpactType
    impact_score: int = Field(ge=-100, le=100)

    headline: str
    explanation: str

    cost_impact: Optional[int] = None
    value_impact: Optional[int] = None
    time_impact_weeks: Optional[int] = None

    required_actions: list[str] = Field(default_factory=list)
    mitigation_options: list[str] = Field(default_factory=list)

    framework_section: Optional[str] = None


# Pre-defined impact rules for common scenarios
TENURE_IMPACTS = {
    "freehold": Impact(
        input_category="title",
        input_field="tenure_confirmed",
        input_value="freehold",
        impact_type=ImpactType.ENABLER,
        impact_score=30,
        headline="Freehold tenure confirmed",
        explanation="Title register confirms freehold tenure - essential for title splitting.",
        framework_section="Section 1: Title Structure Analysis",
    ),
    "leasehold": Impact(
        input_category="title",
        input_field="tenure_confirmed",
        input_value="leasehold",
        impact_type=ImpactType.BLOCKER,
        impact_score=-100,
        headline="BLOCKER: Leasehold tenure",
        explanation="Leasehold tenure prevents title splitting without acquiring freehold first.",
        required_actions=["Do not proceed with title split strategy"],
        framework_section="Section 1: Title Structure Analysis",
    ),
}

SINGLE_TITLE_IMPACTS = {
    True: Impact(
        input_category="title",
        input_field="is_single_title",
        input_value="Yes - all units on single title",
        impact_type=ImpactType.ENABLER,
        impact_score=20,
        headline="Single title confirmed",
        explanation="All units on single freehold title - ideal for splitting.",
        framework_section="Section 1: Title Structure Analysis",
    ),
    False: Impact(
        input_category="title",
        input_field="is_single_title",
        input_value="No - multiple titles exist",
        impact_type=ImpactType.BLOCKER,
        impact_score=-100,
        headline="BLOCKER: Already split",
        explanation="Units already on separate titles - no splitting opportunity.",
        framework_section="Section 1: Title Structure Analysis",
    ),
}

TITLE_CLASS_IMPACTS = {
    "absolute": Impact(
        input_category="title",
        input_field="title_class",
        input_value="Absolute title",
        impact_type=ImpactType.MINOR_POSITIVE,
        impact_score=5,
        headline="Absolute title - best class",
        explanation="Highest level of state guarantee.",
    ),
    "qualified": Impact(
        input_category="title",
        input_field="title_class",
        input_value="Qualified title",
        impact_type=ImpactType.MINOR_NEGATIVE,
        impact_score=-10,
        headline="Qualified title - minor concern",
        explanation="Land Registry has excepted a specific matter. Check what is excepted.",
        cost_impact=500,
        required_actions=["Review the qualification", "Obtain title insurance quote"],
    ),
    "possessory": Impact(
        input_category="title",
        input_field="title_class",
        input_value="Possessory title",
        impact_type=ImpactType.MAJOR_NEGATIVE,
        impact_score=-30,
        headline="Possessory title - requires insurance",
        explanation="Limited state guarantee. Many lenders won't lend on possessory title.",
        cost_impact=1500,
        time_impact_weeks=4,
        required_actions=["Check if title upgrade possible", "Obtain title insurance quote"],
    ),
}

USE_CLASS_IMPACTS = {
    "C3": Impact(
        input_category="planning",
        input_field="current_use_class",
        input_value="C3 (Dwellinghouse)",
        impact_type=ImpactType.ENABLER,
        impact_score=15,
        headline="C3 Use Class - standard residential",
        explanation="Standard residential use. Title split doesn't require planning.",
    ),
    "C4": Impact(
        input_category="planning",
        input_field="current_use_class",
        input_value="C4 (Small HMO)",
        impact_type=ImpactType.MINOR_NEGATIVE,
        impact_score=-10,
        headline="C4 Use Class - small HMO",
        explanation="HMO use. Check Article 4 direction and licensing requirements.",
        required_actions=["Verify Article 4 status", "Confirm HMO licensing"],
    ),
    "sui_generis": Impact(
        input_category="planning",
        input_field="current_use_class",
        input_value="Sui Generis (large HMO)",
        impact_type=ImpactType.MAJOR_NEGATIVE,
        impact_score=-25,
        headline="Sui Generis - complex planning",
        explanation="Large HMO or specialist use. Mandatory HMO licensing applies.",
        cost_impact=2000,
        time_impact_weeks=12,
    ),
}


def assess_charge_impact(charge: ExistingCharge) -> Impact:
    """Assess impact of an existing charge on the title."""
    if charge.consent_likelihood == "refused":
        return Impact(
            input_category="title",
            input_field="existing_charge",
            input_value=f"{charge.lender_name} - consent refused",
            impact_type=ImpactType.BLOCKER,
            impact_score=-100,
            headline=f"BLOCKER: {charge.lender_name} refused consent",
            explanation="Lender has refused consent for title split.",
            required_actions=[
                "Negotiate with lender",
                "Consider full repayment before split",
            ],
        )

    base_score = -15
    if charge.is_all_monies_charge:
        base_score -= 10
    if charge.has_consent_restriction:
        base_score -= 10

    if charge.consent_likelihood == "likely":
        impact_type = ImpactType.MINOR_NEGATIVE
        base_score = -10
    elif charge.consent_likelihood == "unlikely":
        impact_type = ImpactType.MAJOR_NEGATIVE
        base_score = -30
    else:
        impact_type = ImpactType.MAJOR_NEGATIVE

    return Impact(
        input_category="title",
        input_field="existing_charge",
        input_value=f"{charge.lender_name} ({charge.charge_type})",
        impact_type=impact_type,
        impact_score=base_score,
        headline=f"Existing charge: {charge.lender_name}",
        explanation="Lender consent required for title split.",
        cost_impact=charge.consent_fee_quoted or 1500,
        time_impact_weeks=4,
        required_actions=["Apply for lender consent"],
    )


def assess_covenant_impact(covenant: RestrictiveCovenant) -> Impact:
    """Assess impact of a restrictive covenant."""
    if covenant.affects_title_split:
        if covenant.breach_risk == "high":
            return Impact(
                input_category="title",
                input_field="restrictive_covenant",
                input_value=covenant.covenant_summary[:50],
                impact_type=ImpactType.MAJOR_NEGATIVE,
                impact_score=-35,
                headline="Covenant may block split",
                explanation=f"Covenant restricts: {covenant.covenant_summary}",
                cost_impact=covenant.insurance_cost_estimate or 1500,
                required_actions=["Review covenant wording", "Obtain title insurance quote"],
            )
        else:
            return Impact(
                input_category="title",
                input_field="restrictive_covenant",
                input_value=covenant.covenant_summary[:50],
                impact_type=ImpactType.MINOR_NEGATIVE,
                impact_score=-15,
                headline="Covenant noted - review required",
                explanation=f"Covenant: {covenant.covenant_summary}",
                required_actions=["Review with solicitor"],
            )

    return Impact(
        input_category="title",
        input_field="restrictive_covenant",
        input_value="Not affecting split",
        impact_type=ImpactType.NEUTRAL,
        impact_score=0,
        headline="Covenant - not affecting split",
        explanation="Does not appear to affect title splitting.",
    )


def assess_hmo_licensing_impact(hmo: HMOLicensing) -> list[Impact]:
    """Assess impact of HMO licensing status."""
    impacts = []

    if hmo.requires_mandatory_licence:
        if not hmo.licence_held:
            impacts.append(Impact(
                input_category="planning",
                input_field="hmo_mandatory_licence",
                input_value="Required - NO LICENCE",
                impact_type=ImpactType.BLOCKER,
                impact_score=-100,
                headline="BLOCKER: No mandatory HMO licence",
                explanation="Operating without licence is criminal offence.",
                cost_impact=5000,
                required_actions=["Verify licence status", "Factor into negotiation"],
            ))
        else:
            impacts.append(Impact(
                input_category="planning",
                input_field="hmo_mandatory_licence",
                input_value="Required - licence held",
                impact_type=ImpactType.NEUTRAL,
                impact_score=0,
                headline="Mandatory HMO licence in place",
                explanation=f"Licence #{hmo.licence_number} held.",
                required_actions=["Confirm transferability"],
            ))

    if hmo.fire_safety_compliant is False:
        impacts.append(Impact(
            input_category="planning",
            input_field="hmo_fire_safety",
            input_value="Non-compliant",
            impact_type=ImpactType.MAJOR_NEGATIVE,
            impact_score=-35,
            headline="Fire safety non-compliant",
            explanation="Property does not meet fire safety requirements.",
            cost_impact=5000,
            required_actions=["Obtain fire risk assessment", "Budget for works"],
        ))

    return impacts


def assess_physical_impact(physical: PhysicalVerification) -> list[Impact]:
    """Assess impact of physical inspection findings."""
    impacts = []

    # Self-containment check
    non_sc = [u for u in physical.units if u.is_self_contained is False]
    if non_sc:
        unit_names = ", ".join([u.unit_identifier for u in non_sc])
        impacts.append(Impact(
            input_category="physical",
            input_field="self_contained",
            input_value=f"Not self-contained: {unit_names}",
            impact_type=ImpactType.MAJOR_NEGATIVE,
            impact_score=-40,
            headline=f"Units not self-contained: {unit_names}",
            explanation="Self-containment required for mortgageability.",
            cost_impact=10000 * len(non_sc),
            required_actions=["Assess conversion feasibility", "Recalculate values"],
        ))
    elif physical.units and all(u.is_self_contained for u in physical.units if u.is_self_contained is not None):
        impacts.append(Impact(
            input_category="physical",
            input_field="self_contained",
            input_value="All units self-contained",
            impact_type=ImpactType.ENABLER,
            impact_score=25,
            headline="All units self-contained",
            explanation="Each unit has own entrance, kitchen, bathroom.",
        ))

    # Structural concerns
    if physical.structural_concerns:
        impacts.append(Impact(
            input_category="physical",
            input_field="structural_concerns",
            input_value=", ".join(physical.structural_concerns[:2]),
            impact_type=ImpactType.MAJOR_NEGATIVE,
            impact_score=-50,
            headline="Structural concerns identified",
            explanation=f"Issues: {', '.join(physical.structural_concerns)}",
            cost_impact=15000,
            time_impact_weeks=8,
            required_actions=["Commission structural engineer report"],
        ))

    return impacts


def calculate_total_impact(impacts: list[Impact]) -> dict:
    """Calculate total impact from all impacts."""
    total_score = 0
    blockers = []
    total_cost = 0
    total_time_weeks = 0

    for impact in impacts:
        total_score += impact.impact_score
        if impact.impact_type == ImpactType.BLOCKER:
            blockers.append(impact.headline)
        if impact.cost_impact:
            total_cost += impact.cost_impact
        if impact.time_impact_weeks:
            total_time_weeks = max(total_time_weeks, impact.time_impact_weeks)

    return {
        "total_score": total_score,
        "has_blockers": len(blockers) > 0,
        "blockers": blockers,
        "additional_cost": total_cost,
        "timeline_extension_weeks": total_time_weeks,
        "impact_count": len(impacts),
        "positive_count": len([i for i in impacts if i.impact_score > 0]),
        "negative_count": len([i for i in impacts if i.impact_score < 0]),
    }

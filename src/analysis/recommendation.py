from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.models.property import Property
from src.models.manual_inputs import ManualInputs, TitleInputs, PlanningInputs
from src.analysis.screening import ScreeningResult


class RecommendationLevel(str, Enum):
    STRONG_PROCEED = "strong_proceed"
    PROCEED = "proceed"
    PROCEED_WITH_CAUTION = "proceed_caution"
    REVIEW_REQUIRED = "review"
    LIKELY_DECLINE = "likely_decline"
    DECLINE = "decline"
    INSUFFICIENT_DATA = "insufficient"


class RecommendationStage(str, Enum):
    INITIAL = "initial"
    ENRICHED = "enriched"
    PARTIALLY_VERIFIED = "partial"
    FULLY_VERIFIED = "verified"


class Recommendation(BaseModel):
    """Full recommendation with reasoning."""

    level: RecommendationLevel
    stage: RecommendationStage
    confidence: float = Field(ge=0, le=1)

    headline: str
    summary: str

    positive_factors: list[str] = Field(default_factory=list)
    negative_factors: list[str] = Field(default_factory=list)
    unknown_factors: list[str] = Field(default_factory=list)

    hard_blockers: list[str] = Field(default_factory=list)
    soft_blockers: list[str] = Field(default_factory=list)

    required_actions: list[str] = Field(default_factory=list)
    optional_actions: list[str] = Field(default_factory=list)

    estimated_net_benefit: Optional[int] = None
    benefit_confidence: str = "none"

    risk_level: str = "unknown"


def generate_initial_recommendation(
    property: Property,
    screening_result: ScreeningResult,
) -> Recommendation:
    """
    Generate recommendation from scraped data only.

    This runs BEFORE any enrichment or manual input.
    Confidence is low but provides initial signal.
    """
    positive = []
    negative = []
    unknown = []
    hard_blockers = []
    soft_blockers = []

    # === UNIT COUNT ASSESSMENT ===
    if property.estimated_units:
        if 2 <= property.estimated_units <= 6:
            positive.append(f"{property.estimated_units} units - ideal size for title split")
        elif 7 <= property.estimated_units <= 10:
            positive.append(f"{property.estimated_units} units - good size, manageable complexity")
        elif property.estimated_units > 10:
            soft_blockers.append(f"{property.estimated_units} units may be too complex")
    else:
        unknown.append("Unit count unclear from listing - needs verification")

    # === TENURE ASSESSMENT ===
    if property.tenure == "freehold":
        if property.tenure_confidence > 0.8:
            positive.append("Freehold tenure stated in listing")
        else:
            positive.append("Likely freehold (needs title verification)")
    elif property.tenure == "leasehold":
        hard_blockers.append("Leasehold - not suitable for title splitting")
    elif property.tenure == "share_of_freehold":
        hard_blockers.append("Share of freehold - already split, no opportunity")
    else:
        unknown.append("Tenure not stated - critical to verify")

    # === PRICE ASSESSMENT ===
    if property.price_per_unit:
        if property.price_per_unit < 40000:
            positive.append(f"Low entry at £{property.price_per_unit:,}/unit")
        elif property.price_per_unit < 60000:
            positive.append(f"Reasonable pricing at £{property.price_per_unit:,}/unit")
        elif property.price_per_unit < 80000:
            negative.append(f"Higher entry at £{property.price_per_unit:,}/unit")
        else:
            soft_blockers.append(f"Premium pricing at £{property.price_per_unit:,}/unit")

    # === CONDITION INDICATORS ===
    if property.refurb_indicators:
        positive.append("Refurbishment opportunity - value-add potential")

    # === RED FLAGS FROM SCREENING ===
    for rejection in screening_result.rejections:
        if "leasehold" in rejection or "freehold" in rejection:
            hard_blockers.append(rejection.replace("_", " ").title())
        else:
            soft_blockers.append(rejection.replace("_", " ").title())

    for warning in screening_result.warnings:
        negative.append(warning.replace("_", " ").title())

    # === CALCULATE RECOMMENDATION LEVEL ===
    if hard_blockers:
        level = RecommendationLevel.DECLINE
        headline = "Not suitable - deal-breaking issues identified"
    elif len(soft_blockers) >= 2:
        level = RecommendationLevel.LIKELY_DECLINE
        headline = "Significant concerns - likely not viable"
    elif len(unknown) >= 3:
        level = RecommendationLevel.REVIEW_REQUIRED
        headline = "Insufficient data - requires investigation"
    elif len(positive) >= 3 and len(negative) <= 1:
        level = RecommendationLevel.PROCEED
        headline = "Promising opportunity - proceed to due diligence"
    elif len(positive) >= 2:
        level = RecommendationLevel.PROCEED_WITH_CAUTION
        headline = "Potential opportunity - verify key items"
    else:
        level = RecommendationLevel.REVIEW_REQUIRED
        headline = "Mixed signals - requires deeper analysis"

    # === DETERMINE REQUIRED ACTIONS ===
    required_actions = []
    if "tenure" in str(unknown).lower() or property.tenure == "unknown":
        required_actions.append("Verify freehold tenure via Land Registry (£3)")
    if property.estimated_units is None:
        required_actions.append("Confirm unit count from EPC data or viewing")
    required_actions.append("Order title register to check for charges/restrictions")

    optional_actions = [
        "Request agent call for more details",
        "Check planning portal for history",
        "Review EPC certificates for each unit",
    ]

    summary = _generate_summary(level, positive, negative, unknown)

    return Recommendation(
        level=level,
        stage=RecommendationStage.INITIAL,
        confidence=0.4,
        headline=headline,
        summary=summary,
        positive_factors=positive,
        negative_factors=negative,
        unknown_factors=unknown,
        hard_blockers=hard_blockers,
        soft_blockers=soft_blockers,
        required_actions=required_actions,
        optional_actions=optional_actions,
        estimated_net_benefit=None,
        benefit_confidence="none",
        risk_level="unknown",
    )


def generate_enriched_recommendation(
    property: Property,
    epc_count: int,
    comparable_count: int,
    estimated_uplift: Optional[int],
) -> Recommendation:
    """
    Generate recommendation after EPC and comparable enrichment.
    """
    positive = []
    negative = []
    unknown = []
    hard_blockers = []
    soft_blockers = []

    # Start with base factors
    if property.tenure == "freehold":
        positive.append("Freehold tenure confirmed/likely")
    elif property.tenure == "leasehold":
        hard_blockers.append("Leasehold tenure")

    if property.estimated_units and 2 <= property.estimated_units <= 8:
        positive.append(f"{property.estimated_units} units - suitable scale")

    # EPC data quality
    if epc_count >= (property.estimated_units or 0):
        positive.append(f"EPC data found for all {epc_count} units")
    elif epc_count > 0:
        negative.append(f"Only {epc_count} EPCs found - may be missing units")
    else:
        unknown.append("No EPC data - floor areas unverified")

    # Comparable evidence
    if comparable_count >= 10:
        positive.append(f"Strong comparable evidence ({comparable_count} sales)")
    elif comparable_count >= 5:
        positive.append(f"Good comparable evidence ({comparable_count} sales)")
    elif comparable_count >= 3:
        negative.append(f"Limited comparables ({comparable_count} sales)")
    else:
        unknown.append("Insufficient comparable sales data")

    # Financial assessment
    if estimated_uplift:
        if estimated_uplift >= 50000:
            positive.append(f"Strong gross uplift potential: £{estimated_uplift:,}")
        elif estimated_uplift >= 25000:
            positive.append(f"Good gross uplift potential: £{estimated_uplift:,}")
        elif estimated_uplift >= 10000:
            negative.append(f"Modest uplift potential: £{estimated_uplift:,}")
        else:
            soft_blockers.append(f"Limited uplift: £{estimated_uplift:,}")

    # EPC rating opportunity
    if property.avg_epc_rating in ["E", "F", "G"]:
        positive.append(f"Average EPC {property.avg_epc_rating} - EPC uplift opportunity")
    elif property.avg_epc_rating in ["D"]:
        positive.append("EPC D - some improvement potential")

    # Calculate level
    if hard_blockers:
        level = RecommendationLevel.DECLINE
        headline = "Not viable - critical issues identified"
    elif len(soft_blockers) >= 2:
        level = RecommendationLevel.LIKELY_DECLINE
        headline = "Marginal opportunity - significant concerns"
    elif len(positive) >= 4 and not negative:
        level = RecommendationLevel.STRONG_PROCEED
        headline = "Strong opportunity - priority for due diligence"
    elif len(positive) >= 3:
        level = RecommendationLevel.PROCEED
        headline = "Good opportunity - proceed to verification"
    elif len(positive) >= 2:
        level = RecommendationLevel.PROCEED_WITH_CAUTION
        headline = "Potential opportunity - address concerns"
    else:
        level = RecommendationLevel.REVIEW_REQUIRED
        headline = "Further investigation needed"

    # Confidence based on data quality
    confidence = 0.5
    if epc_count >= (property.estimated_units or 0):
        confidence += 0.1
    if comparable_count >= 5:
        confidence += 0.1
    if estimated_uplift:
        confidence += 0.1

    required_actions = [
        "Order official title copies from Land Registry",
        "Arrange viewing to verify unit layout",
        "Check planning portal for conversion consent",
    ]

    return Recommendation(
        level=level,
        stage=RecommendationStage.ENRICHED,
        confidence=min(confidence, 0.8),
        headline=headline,
        summary=_generate_summary(level, positive, negative, unknown),
        positive_factors=positive,
        negative_factors=negative,
        unknown_factors=unknown,
        hard_blockers=hard_blockers,
        soft_blockers=soft_blockers,
        required_actions=required_actions,
        optional_actions=[],
        estimated_net_benefit=estimated_uplift,
        benefit_confidence="medium" if comparable_count >= 5 else "low",
        risk_level="medium",
    )


def generate_verified_recommendation(
    property: Property,
    manual_inputs: ManualInputs,
    estimated_net_benefit: Optional[int],
) -> Recommendation:
    """
    Generate recommendation after manual verification.
    """
    positive = []
    negative = []
    hard_blockers = []
    soft_blockers = []

    # Title verification
    if manual_inputs.title.verification:
        tv = manual_inputs.title.verification
        if tv.tenure_confirmed == "freehold":
            positive.append("Freehold tenure verified via Land Registry")
        elif tv.tenure_confirmed == "leasehold":
            hard_blockers.append("Leasehold tenure - not suitable")

        if tv.is_single_title is True:
            positive.append("Single title confirmed - clear for splitting")
        elif tv.is_single_title is False:
            hard_blockers.append("Already split into multiple titles")

        if tv.title_class == "absolute":
            positive.append("Absolute title class - best quality")
        elif tv.title_class == "possessory":
            soft_blockers.append("Possessory title - requires insurance")

    # Charges assessment
    for charge in manual_inputs.title.charges:
        if charge.consent_likelihood == "refused":
            hard_blockers.append(f"Lender consent refused: {charge.lender_name}")
        elif charge.consent_likelihood == "unlikely":
            soft_blockers.append(f"Lender consent unlikely: {charge.lender_name}")
        elif charge.consent_likelihood == "likely":
            positive.append(f"Lender consent likely: {charge.lender_name}")

    # Covenants assessment
    for covenant in manual_inputs.title.covenants:
        if covenant.affects_title_split and covenant.breach_risk == "high":
            hard_blockers.append(f"Covenant blocks split: {covenant.covenant_summary}")
        elif covenant.affects_title_split:
            soft_blockers.append(f"Covenant concern: {covenant.covenant_summary}")

    # Planning assessment
    if manual_inputs.planning.planning_status:
        ps = manual_inputs.planning.planning_status
        if ps.current_use_class == "C3":
            positive.append("C3 use class confirmed")
        elif ps.current_use_class == "sui generis":
            soft_blockers.append("Sui generis use class - may complicate")

        if ps.original_conversion_consented is True:
            positive.append("Original conversion properly consented")
        elif ps.original_conversion_consented is False:
            hard_blockers.append("Conversion not consented - regularisation needed")

    # HMO licensing
    if manual_inputs.planning.hmo_licensing:
        hmo = manual_inputs.planning.hmo_licensing
        if hmo.requires_mandatory_licence and not hmo.licence_held:
            hard_blockers.append("HMO licence required but not held")

    # Physical verification
    if manual_inputs.physical:
        all_self_contained = all(
            u.is_self_contained for u in manual_inputs.physical.units
            if u.is_self_contained is not None
        )
        if all_self_contained:
            positive.append("All units verified as self-contained")
        elif any(u.is_self_contained is False for u in manual_inputs.physical.units):
            hard_blockers.append("Not all units self-contained")

    # Manual flags
    hard_blockers.extend(manual_inputs.manual_red_flags)
    positive.extend(manual_inputs.manual_green_flags)

    # Calculate level
    if hard_blockers:
        level = RecommendationLevel.DECLINE
        headline = "Do not proceed - verified blockers present"
    elif len(soft_blockers) >= 2:
        level = RecommendationLevel.LIKELY_DECLINE
        headline = "Significant verified concerns - likely not viable"
    elif len(positive) >= 5 and not soft_blockers:
        level = RecommendationLevel.STRONG_PROCEED
        headline = "Verified opportunity - proceed to purchase"
    elif len(positive) >= 4:
        level = RecommendationLevel.PROCEED
        headline = "Good verified opportunity - proceed"
    else:
        level = RecommendationLevel.PROCEED_WITH_CAUTION
        headline = "Proceed with noted concerns"

    return Recommendation(
        level=level,
        stage=RecommendationStage.FULLY_VERIFIED,
        confidence=0.9 if not hard_blockers else 0.95,
        headline=headline,
        summary=_generate_summary(level, positive, negative, []),
        positive_factors=positive,
        negative_factors=negative,
        unknown_factors=[],
        hard_blockers=hard_blockers,
        soft_blockers=soft_blockers,
        required_actions=["Proceed to offer" if not hard_blockers else "Do not proceed"],
        optional_actions=[],
        estimated_net_benefit=estimated_net_benefit,
        benefit_confidence="high" if estimated_net_benefit else "medium",
        risk_level="low" if len(positive) > len(soft_blockers) else "medium",
    )


def _generate_summary(
    level: RecommendationLevel,
    positive: list[str],
    negative: list[str],
    unknown: list[str],
) -> str:
    """Generate a 2-3 sentence summary."""
    if level == RecommendationLevel.DECLINE:
        return "This property has critical issues that make it unsuitable for title splitting. Do not proceed."

    if level == RecommendationLevel.STRONG_PROCEED:
        return (
            f"Strong opportunity with {len(positive)} positive factors identified. "
            "Recommend proceeding to due diligence as a priority."
        )

    if level == RecommendationLevel.PROCEED:
        return (
            f"Good opportunity with {len(positive)} positive factors. "
            f"{'Minor concerns to address.' if negative else 'No significant concerns.'}"
        )

    if level == RecommendationLevel.PROCEED_WITH_CAUTION:
        return (
            f"Potential opportunity but {len(negative)} concerns noted. "
            "Verify key items before committing."
        )

    if level == RecommendationLevel.REVIEW_REQUIRED:
        return (
            f"Mixed signals with {len(unknown)} unknown factors. "
            "Further investigation required before assessment."
        )

    return "Assessment pending - insufficient data for recommendation."

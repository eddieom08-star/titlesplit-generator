## CHUNK 15: Impact Assessment Engine

### 15.1 Impact Definitions

```python
# src/analysis/impact_rules.py

from enum import Enum
from typing import Callable, Optional
from pydantic import BaseModel


class ImpactType(str, Enum):
    BLOCKER = "blocker"           # Deal cannot proceed
    MAJOR_NEGATIVE = "major_neg"  # Significant concern, may still proceed
    MINOR_NEGATIVE = "minor_neg"  # Small concern, factor into pricing
    NEUTRAL = "neutral"           # No material impact
    MINOR_POSITIVE = "minor_pos"  # Small benefit
    MAJOR_POSITIVE = "major_pos"  # Significant benefit
    ENABLER = "enabler"           # Removes uncertainty, de-risks


class Impact(BaseModel):
    """Assessment of how a manual input impacts the deal."""
    
    input_category: str  # title, planning, physical, financial
    input_field: str     # The specific field that was entered
    input_value: str     # What was entered (summarised)
    
    impact_type: ImpactType
    impact_score: int    # -100 to +100
    
    headline: str        # "Existing charge requires lender consent"
    explanation: str     # Detailed explanation of impact
    
    # Financial impact (if quantifiable)
    cost_impact: Optional[int] = None      # Additional costs
    value_impact: Optional[int] = None     # Change to expected value
    time_impact_weeks: Optional[int] = None  # Delay to timeline
    
    # Actions
    required_actions: list[str] = []
    mitigation_options: list[str] = []
    
    # Framework reference
    framework_section: Optional[str] = None  # Reference to framework section


# ============================================================================
# TITLE IMPACT RULES
# ============================================================================

TITLE_IMPACT_RULES = {
    
    # === TENURE CONFIRMATION ===
    "tenure_confirmed": {
        "freehold": Impact(
            input_category="title",
            input_field="tenure_confirmed",
            input_value="freehold",
            impact_type=ImpactType.ENABLER,
            impact_score=30,
            headline="Freehold tenure confirmed ✓",
            explanation=(
                "Title register confirms freehold tenure. This is essential for "
                "title splitting - you own the building outright and can grant "
                "new leases without restriction from a superior landlord."
            ),
            required_actions=[],
            mitigation_options=[],
            framework_section="Section 1: Title Structure Analysis"
        ),
        "leasehold": Impact(
            input_category="title",
            input_field="tenure_confirmed",
            input_value="leasehold",
            impact_type=ImpactType.BLOCKER,
            impact_score=-100,
            headline="BLOCKER: Leasehold tenure - cannot proceed",
            explanation=(
                "Title register shows leasehold tenure. Title splitting requires "
                "freehold ownership to grant new leases. A leasehold interest cannot "
                "be split further without the freeholder's cooperation, which is "
                "rarely given and would involve acquiring the freehold first."
            ),
            required_actions=[
                "Do not proceed with this strategy",
                "Consider if collective enfranchisement is viable (different strategy)"
            ],
            mitigation_options=[],
            framework_section="Section 1: Title Structure Analysis"
        ),
    },
    
    # === SINGLE TITLE CONFIRMATION ===
    "is_single_title": {
        True: Impact(
            input_category="title",
            input_field="is_single_title",
            input_value="Yes - all units on single title",
            impact_type=ImpactType.ENABLER,
            impact_score=20,
            headline="Single title confirmed ✓",
            explanation=(
                "All units are on a single freehold title. This is the ideal "
                "starting point for title splitting - one acquisition gives you "
                "control of all units."
            ),
            required_actions=[],
            mitigation_options=[],
            framework_section="Section 1: Title Structure Analysis"
        ),
        False: Impact(
            input_category="title",
            input_field="is_single_title",
            input_value="No - multiple titles exist",
            impact_type=ImpactType.BLOCKER,
            impact_score=-100,
            headline="BLOCKER: Units already on separate titles",
            explanation=(
                "The units are already on separate titles. There is no title "
                "splitting opportunity - the work has already been done. "
                "The listing may be misleading, or this is being sold as "
                "individual units rather than a block."
            ),
            required_actions=[
                "Verify listing accuracy with agent",
                "Consider if this is actually a share of freehold structure"
            ],
            mitigation_options=[],
            framework_section="Section 1: Title Structure Analysis"
        ),
    },
    
    # === TITLE CLASS ===
    "title_class": {
        "absolute": Impact(
            input_category="title",
            input_field="title_class",
            input_value="Absolute title",
            impact_type=ImpactType.MINOR_POSITIVE,
            impact_score=5,
            headline="Absolute title - best class ✓",
            explanation=(
                "Absolute title is the best class of title, giving the highest "
                "level of state guarantee. No additional concerns from title class."
            ),
            required_actions=[],
            mitigation_options=[],
            framework_section="Section 6: Risk Assessment - Title Quality"
        ),
        "qualified": Impact(
            input_category="title",
            input_field="title_class",
            input_value="Qualified title",
            impact_type=ImpactType.MINOR_NEGATIVE,
            impact_score=-10,
            headline="Qualified title - minor concern",
            explanation=(
                "Qualified title means the Land Registry has excepted a specific "
                "matter from the state guarantee. Check what is excepted. This "
                "may affect lender appetite and could require title insurance."
            ),
            cost_impact=500,  # Typical title insurance
            required_actions=[
                "Review the qualification - what is excepted?",
                "Obtain title insurance quote"
            ],
            mitigation_options=[
                "Title indemnity insurance (typically £200-500)"
            ],
            framework_section="Section 6: Risk Assessment - Title Quality"
        ),
        "possessory": Impact(
            input_category="title",
            input_field="title_class",
            input_value="Possessory title",
            impact_type=ImpactType.MAJOR_NEGATIVE,
            impact_score=-30,
            headline="Possessory title - requires upgrade or insurance",
            explanation=(
                "Possessory title offers limited state guarantee. The registered "
                "owner's title is based on possession, not documentary proof. "
                "Many lenders will not lend on possessory title, limiting your "
                "refinancing options. Consider applying for title upgrade if "
                "12+ years possession, or budget for title insurance."
            ),
            cost_impact=1500,  # Title insurance for possessory
            time_impact_weeks=4,  # If applying for upgrade
            required_actions=[
                "Check if title upgrade possible (12+ years possession)",
                "Obtain title insurance quote",
                "Verify target lenders will accept possessory title"
            ],
            mitigation_options=[
                "Apply for title upgrade (ST1 form) - takes 4-8 weeks",
                "Title indemnity insurance (higher premium, ~£1000-2000)"
            ],
            framework_section="Section 6: Risk Assessment - Title Quality"
        ),
    },
}


# ============================================================================
# CHARGES IMPACT RULES
# ============================================================================

def assess_charge_impact(charge: ExistingCharge) -> Impact:
    """Assess impact of an existing charge on the title."""
    
    # Start with base impact for any charge
    base_score = -15
    cost_impact = 0
    time_impact = 0
    required_actions = []
    mitigation_options = []
    
    # All-monies charge is more complex
    if charge.is_all_monies_charge:
        base_score -= 10
        explanation_extra = (
            "This is an all-monies charge, meaning the security covers all "
            "amounts owed to the lender, not just this specific loan. Release "
            "mechanics may be more complex."
        )
    else:
        explanation_extra = ""
    
    # Consent restriction
    if charge.has_consent_restriction:
        required_actions.append("Apply for lender consent before proceeding")
        cost_impact += 1500  # Typical consent + legal fees
        time_impact += 4  # Weeks
    
    # Based on consent likelihood
    if charge.consent_likelihood == "refused":
        return Impact(
            input_category="title",
            input_field="existing_charge",
            input_value=f"{charge.lender_name} - consent refused",
            impact_type=ImpactType.BLOCKER,
            impact_score=-100,
            headline=f"BLOCKER: {charge.lender_name} refused consent",
            explanation=(
                f"The existing lender ({charge.lender_name}) has refused consent "
                f"for the title split. Without their agreement, you cannot proceed "
                f"while their charge remains on the title."
            ),
            required_actions=[
                "Negotiate with lender - understand their objections",
                "Consider if full repayment is viable before split",
                "Explore alternative lenders who will refinance the whole block"
            ],
            mitigation_options=[
                "Repay existing facility and remove charge",
                "Negotiate terms that satisfy lender concerns"
            ],
            framework_section="Section 4: Lender Consent Protocol"
        )
    
    elif charge.consent_likelihood == "unlikely":
        base_score -= 20
        impact_type = ImpactType.MAJOR_NEGATIVE
        headline = f"Lender consent unlikely: {charge.lender_name}"
        required_actions.append("Engage solicitor to negotiate with lender")
        required_actions.append("Prepare alternative financing strategy")
    
    elif charge.consent_likelihood == "likely":
        impact_type = ImpactType.MINOR_NEGATIVE
        headline = f"Existing charge: {charge.lender_name} (consent likely)"
        base_score = -10
    
    elif charge.consent_likelihood == "uncertain":
        impact_type = ImpactType.MAJOR_NEGATIVE
        headline = f"Existing charge: {charge.lender_name} (consent uncertain)"
        base_score = -20
        required_actions.append("Contact lender to assess consent likelihood")
    
    else:
        impact_type = ImpactType.MAJOR_NEGATIVE
        headline = f"Existing charge: {charge.lender_name} (consent not yet sought)"
        required_actions.append("Contact lender regarding consent requirements")
    
    # Add consent fee if known
    if charge.consent_fee_quoted:
        cost_impact += charge.consent_fee_quoted
    
    return Impact(
        input_category="title",
        input_field="existing_charge",
        input_value=f"{charge.lender_name} ({charge.charge_type})",
        impact_type=impact_type,
        impact_score=base_score,
        headline=headline,
        explanation=(
            f"There is an existing {charge.charge_type} from {charge.lender_name} "
            f"registered against the title. You will need their consent to proceed "
            f"with the title split, and they may require security adjustments or "
            f"partial repayment. {explanation_extra}"
        ),
        cost_impact=cost_impact,
        time_impact_weeks=time_impact,
        required_actions=required_actions,
        mitigation_options=[
            "Engage early with lender",
            "Prepare updated valuations showing security position",
            "Consider refinancing entire facility with split-friendly lender"
        ],
        framework_section="Section 4: Lender Consent Protocol"
    )


# ============================================================================
# RESTRICTIVE COVENANT IMPACT RULES
# ============================================================================

def assess_covenant_impact(covenant: RestrictiveCovenant) -> Impact:
    """Assess impact of a restrictive covenant."""
    
    # Use restriction (most common issue)
    if covenant.covenant_type == "use_restriction":
        if covenant.affects_title_split:
            return Impact(
                input_category="title",
                input_field="restrictive_covenant",
                input_value=f"Use restriction: {covenant.covenant_summary[:50]}",
                impact_type=ImpactType.MAJOR_NEGATIVE,
                impact_score=-25,
                headline="Use restriction may affect split",
                explanation=(
                    f"The covenant restricts use of the property: '{covenant.covenant_summary}'. "
                    f"This may affect your ability to grant new leases or the terms you can include. "
                    f"Review whether the split would breach the covenant."
                ),
                cost_impact=covenant.insurance_cost_estimate or 1000,
                required_actions=[
                    "Review covenant wording with solicitor",
                    "Assess if split would constitute breach",
                    "Identify covenant beneficiary"
                ],
                mitigation_options=[
                    f"Title indemnity insurance: ~£{covenant.insurance_cost_estimate or 1000}",
                    "Apply to Lands Tribunal to modify/discharge (expensive, slow)",
                    "Approach beneficiary for release"
                ],
                framework_section="Section 6: Risk Assessment - Title Quality"
            )
        else:
            return Impact(
                input_category="title",
                input_field="restrictive_covenant",
                input_value=f"Use restriction (not affecting split)",
                impact_type=ImpactType.NEUTRAL,
                impact_score=0,
                headline="Use restriction - not affecting split ✓",
                explanation=(
                    f"The covenant '{covenant.covenant_summary}' does not appear "
                    f"to affect the title splitting strategy."
                ),
                required_actions=[],
                mitigation_options=[],
                framework_section="Section 6: Risk Assessment - Title Quality"
            )
    
    # Alienation restriction
    elif covenant.covenant_type == "alienation":
        return Impact(
            input_category="title",
            input_field="restrictive_covenant",
            input_value="Alienation covenant",
            impact_type=ImpactType.MAJOR_NEGATIVE,
            impact_score=-35,
            headline="Alienation covenant restricts disposals",
            explanation=(
                f"There is a covenant restricting alienation (disposal): "
                f"'{covenant.covenant_summary}'. This could prevent you from "
                f"granting new leases or require third-party consent. This is "
                f"a significant concern for title splitting."
            ),
            cost_impact=2000,  # Insurance or release costs
            required_actions=[
                "Assess exact scope of restriction",
                "Identify if consent mechanism exists",
                "Budget for release or insurance"
            ],
            mitigation_options=[
                "Obtain consent from covenant beneficiary",
                "Title indemnity insurance (if historic covenant)",
                "Legal opinion on enforceability"
            ],
            framework_section="Section 6: Risk Assessment - Title Quality"
        )
    
    # Building restriction
    elif covenant.covenant_type == "building_restriction":
        return Impact(
            input_category="title",
            input_field="restrictive_covenant",
            input_value=f"Building restriction",
            impact_type=ImpactType.MINOR_NEGATIVE if covenant.breach_risk == "low" else ImpactType.MAJOR_NEGATIVE,
            impact_score=-10 if covenant.breach_risk == "low" else -25,
            headline=f"Building covenant - {covenant.breach_risk} breach risk",
            explanation=(
                f"Building covenant: '{covenant.covenant_summary}'. If the property "
                f"has already been converted to flats, there may be a historic breach. "
                f"Consider title insurance to cover this."
            ),
            cost_impact=500 if covenant.breach_risk == "low" else 1500,
            required_actions=[
                "Check if conversion predates covenant",
                "Assess if title insurance available"
            ],
            mitigation_options=[
                "Title indemnity insurance for historic breach",
                "Statutory declaration if breach >20 years"
            ],
            framework_section="Section 6: Risk Assessment - Title Quality"
        )
    
    else:
        return Impact(
            input_category="title",
            input_field="restrictive_covenant",
            input_value=covenant.covenant_summary[:50],
            impact_type=ImpactType.MINOR_NEGATIVE,
            impact_score=-5,
            headline="Covenant noted - review required",
            explanation=f"Covenant: {covenant.covenant_summary}",
            required_actions=["Review covenant with solicitor"],
            mitigation_options=[],
            framework_section="Section 6: Risk Assessment - Title Quality"
        )


# ============================================================================
# PLANNING IMPACT RULES
# ============================================================================

PLANNING_IMPACT_RULES = {
    
    "current_use_class": {
        "C3": Impact(
            input_category="planning",
            input_field="current_use_class",
            input_value="C3 (Dwellinghouse)",
            impact_type=ImpactType.ENABLER,
            impact_score=15,
            headline="C3 Use Class - standard residential ✓",
            explanation=(
                "The property is in C3 use class (dwellinghouse). This is the "
                "standard residential use class. Splitting the title does not "
                "require planning permission as it's a legal, not physical change."
            ),
            required_actions=[],
            mitigation_options=[],
            framework_section="Section 1: Property Schedule"
        ),
        "C4": Impact(
            input_category="planning",
            input_field="current_use_class",
            input_value="C4 (Small HMO)",
            impact_type=ImpactType.MINOR_NEGATIVE,
            impact_score=-10,
            headline="C4 Use Class - small HMO",
            explanation=(
                "The property has C4 (small HMO) use. This is fine for rental "
                "but may affect future sales as owner-occupiers prefer C3. "
                "Check if the area has Article 4 direction affecting C4 use. "
                "Title splitting itself doesn't require planning but maintaining "
                "HMO use after split may be complex."
            ),
            required_actions=[
                "Verify if Article 4 direction applies",
                "Confirm HMO licensing requirements"
            ],
            mitigation_options=[
                "Apply for C3 use if converting away from HMO",
                "Budget for HMO licence transfer"
            ],
            framework_section="Section 8: HMO Portfolios"
        ),
        "sui_generis": Impact(
            input_category="planning",
            input_field="current_use_class",
            input_value="Sui Generis (large HMO or other)",
            impact_type=ImpactType.MAJOR_NEGATIVE,
            impact_score=-25,
            headline="Sui Generis use - complex planning position",
            explanation=(
                "Sui generis use (outside standard use classes) typically indicates "
                "a large HMO (7+ bedrooms) or other specialist use. This creates "
                "complexity: changing use after title split may require planning "
                "permission, and individual unit sales may be restricted. "
                "Mandatory HMO licensing will apply."
            ),
            cost_impact=2000,  # Potential planning application
            time_impact_weeks=12,  # If planning needed
            required_actions=[
                "Confirm exact current use",
                "Assess if HMO licensing transfers",
                "Budget for potential planning application"
            ],
            mitigation_options=[
                "Maintain current use and sell as investment",
                "Apply for C3 conversion (if physically feasible)"
            ],
            framework_section="Section 8: HMO Portfolios"
        ),
    },
    
    "original_conversion_consented": {
        True: Impact(
            input_category="planning",
            input_field="original_conversion_consented",
            input_value="Yes - conversion properly consented",
            impact_type=ImpactType.ENABLER,
            impact_score=20,
            headline="Conversion fully consented ✓",
            explanation=(
                "The conversion of the property to flats has proper planning "
                "consent. This removes a significant risk and means the flats "
                "are lawful units that can be mortgaged and sold individually."
            ),
            required_actions=[],
            mitigation_options=[],
            framework_section="Section 1: Property Schedule - Planning Status"
        ),
        False: Impact(
            input_category="planning",
            input_field="original_conversion_consented",
            input_value="No - conversion not properly consented",
            impact_type=ImpactType.MAJOR_NEGATIVE,
            impact_score=-40,
            headline="WARNING: Conversion may not be lawful",
            explanation=(
                "The conversion to flats may not have planning consent. This is "
                "a significant issue: the flats may not be lawful units, which "
                "affects mortgageability and sale potential. However, if the "
                "conversion was more than 4 years ago, you may be able to obtain "
                "a Certificate of Lawfulness (CLEUD)."
            ),
            cost_impact=1500,  # CLEUD application
            time_impact_weeks=8,
            required_actions=[
                "Determine when conversion took place",
                "Apply for CLEUD if >4 years ago",
                "Check building regulations compliance"
            ],
            mitigation_options=[
                "Certificate of Lawfulness (CLEUD) - £462 fee",
                "Retrospective planning if <4 years",
                "Title indemnity insurance (if CLEUD obtained)"
            ],
            framework_section="Section 1: Property Schedule - Planning Status"
        ),
    },
    
    "building_regs_signed_off": {
        True: Impact(
            input_category="planning",
            input_field="building_regs_signed_off",
            input_value="Yes - building regs signed off",
            impact_type=ImpactType.MINOR_POSITIVE,
            impact_score=10,
            headline="Building regulations compliant ✓",
            explanation=(
                "Building regulations completion certificate has been issued. "
                "This confirms the conversion meets safety and construction "
                "standards, which is important for lenders and buyers."
            ),
            required_actions=[],
            mitigation_options=[],
            framework_section="Section 6: Risk Assessment"
        ),
        False: Impact(
            input_category="planning",
            input_field="building_regs_signed_off",
            input_value="No - building regs not signed off",
            impact_type=ImpactType.MAJOR_NEGATIVE,
            impact_score=-30,
            headline="Building regulations not signed off",
            explanation=(
                "There is no building regulations completion certificate. This is "
                "common in older conversions but creates issues: lenders may "
                "refuse to lend, and there may be safety concerns. You can "
                "obtain regularisation (if compliant) or indemnity insurance."
            ),
            cost_impact=2000,  # Regularisation or insurance
            required_actions=[
                "Commission building regs assessment",
                "Obtain indemnity insurance quote",
                "Budget for any remedial works"
            ],
            mitigation_options=[
                "Building regulations regularisation application",
                "Indemnity insurance for lack of building regs",
                "Remedial works to bring up to standard"
            ],
            framework_section="Section 6: Risk Assessment"
        ),
    },
    
    "in_article_4_area": {
        True: Impact(
            input_category="planning",
            input_field="in_article_4_area",
            input_value="Yes - Article 4 direction applies",
            impact_type=ImpactType.MINOR_NEGATIVE,
            impact_score=-10,
            headline="Article 4 area - permitted development restricted",
            explanation=(
                "The property is in an Article 4 area, which restricts permitted "
                "development rights. This mainly affects future changes (e.g., "
                "converting from HMO back to C3 would need planning permission). "
                "Title splitting itself is not affected as it's a legal change."
            ),
            required_actions=[
                "Note Article 4 restrictions for future planning"
            ],
            mitigation_options=[],
            framework_section="Section 8: HMO Portfolios"
        ),
        False: Impact(
            input_category="planning",
            input_field="in_article_4_area",
            input_value="No - standard permitted development applies",
            impact_type=ImpactType.NEUTRAL,
            impact_score=0,
            headline="No Article 4 restriction ✓",
            explanation="Standard permitted development rights apply.",
            required_actions=[],
            mitigation_options=[],
            framework_section="Section 8: HMO Portfolios"
        ),
    },
}


# ============================================================================
# HMO LICENSING IMPACT RULES
# ============================================================================

def assess_hmo_licensing_impact(hmo: HMOLicensing) -> list[Impact]:
    """Assess impact of HMO licensing status."""
    
    impacts = []
    
    # Mandatory licensing requirement
    if hmo.requires_mandatory_licence:
        if hmo.licence_held:
            impacts.append(Impact(
                input_category="planning",
                input_field="hmo_mandatory_licence",
                input_value="Required - licence held ✓",
                impact_type=ImpactType.NEUTRAL,
                impact_score=0,
                headline="Mandatory HMO licence in place ✓",
                explanation=(
                    f"The property requires a mandatory HMO licence and this is held "
                    f"(#{hmo.licence_number}, expires {hmo.licence_expiry}). "
                    f"Check transferability to new owner."
                ),
                required_actions=[
                    "Confirm licence can transfer to new owner",
                    "Note any conditions requiring compliance"
                ],
                mitigation_options=[],
                framework_section="Section 8: HMO Portfolios"
            ))
        else:
            impacts.append(Impact(
                input_category="planning",
                input_field="hmo_mandatory_licence",
                input_value="Required - NO LICENCE",
                impact_type=ImpactType.BLOCKER,
                impact_score=-100,
                headline="BLOCKER: Operating without mandatory HMO licence",
                explanation=(
                    "The property requires a mandatory HMO licence but does not have one. "
                    "Operating without a licence is a criminal offence. The council can "
                    "issue penalties up to £30,000 and tenants can claim back rent. "
                    "You must either obtain a licence before purchase or negotiate "
                    "significant price reduction to reflect the risk."
                ),
                cost_impact=5000,  # Licence fee + compliance works
                required_actions=[
                    "Verify licence status with council",
                    "Assess compliance works needed",
                    "Factor into negotiation (significant discount required)"
                ],
                mitigation_options=[
                    "Make purchase conditional on licence being obtained",
                    "Negotiate price reduction to reflect risk",
                    "Walk away - this is a major red flag"
                ],
                framework_section="Section 8: HMO Portfolios"
            ))
    
    # Selective licensing
    if hmo.requires_selective_licence:
        if not hmo.licence_held:
            impacts.append(Impact(
                input_category="planning",
                input_field="hmo_selective_licence",
                input_value="Selective licensing applies - no licence",
                impact_type=ImpactType.MAJOR_NEGATIVE,
                impact_score=-30,
                headline="Selective licensing area - licence needed",
                explanation=(
                    "The property is in a selective licensing area and no licence "
                    "is held. While less severe than mandatory licensing, this "
                    "still carries penalties and must be resolved."
                ),
                cost_impact=1500,
                required_actions=[
                    "Apply for selective licence",
                    "Budget for compliance works"
                ],
                mitigation_options=[
                    "Make purchase conditional on licence"
                ],
                framework_section="Section 8: HMO Portfolios"
            ))
    
    # Fire safety compliance
    if hmo.requires_mandatory_licence or hmo.requires_additional_licence:
        if hmo.fire_safety_compliant is False:
            impacts.append(Impact(
                input_category="planning",
                input_field="hmo_fire_safety",
                input_value="Fire safety non-compliant",
                impact_type=ImpactType.MAJOR_NEGATIVE,
                impact_score=-35,
                headline="Fire safety not compliant",
                explanation=(
                    "The property does not meet fire safety requirements for HMO "
                    "licensing. This typically requires fire doors, escape routes, "
                    "alarms, and emergency lighting. Budget for remedial works."
                ),
                cost_impact=5000,  # Typical fire safety works
                required_actions=[
                    "Obtain fire risk assessment",
                    "Budget for fire safety works",
                    "Factor into purchase price"
                ],
                mitigation_options=[
                    "Negotiate price reduction",
                    "Request seller completes works before completion"
                ],
                framework_section="Section 8: HMO Portfolios"
            ))
    
    return impacts


# ============================================================================
# PHYSICAL VERIFICATION IMPACT RULES  
# ============================================================================

def assess_physical_impact(physical: PhysicalVerification) -> list[Impact]:
    """Assess impact of physical inspection findings."""
    
    impacts = []
    
    # Self-containment check
    non_self_contained_units = [
        u for u in physical.units 
        if u.is_self_contained is False
    ]
    
    if non_self_contained_units:
        unit_names = ", ".join([u.unit_identifier for u in non_self_contained_units])
        impacts.append(Impact(
            input_category="physical",
            input_field="self_contained",
            input_value=f"Units not self-contained: {unit_names}",
            impact_type=ImpactType.MAJOR_NEGATIVE,
            impact_score=-40,
            headline=f"Units not self-contained: {unit_names}",
            explanation=(
                f"The following units are not fully self-contained: {unit_names}. "
                f"Self-containment (own entrance, kitchen, bathroom) is important "
                f"for mortgageability and sale value. Non-self-contained units may "
                f"only be mortgageable as HMO rooms, significantly affecting value."
            ),
            cost_impact=10000 * len(non_self_contained_units),  # To make self-contained
            required_actions=[
                "Assess feasibility of creating self-containment",
                "Budget for conversion works",
                "Recalculate unit values as non-self-contained"
            ],
            mitigation_options=[
                "Budget for works to create self-containment",
                "Sell as HMO rooms (lower value)",
                "Negotiate significant price reduction"
            ],
            framework_section="Section 1: Property Schedule - Self-containment"
        ))
    else:
        if physical.units and all(u.is_self_contained for u in physical.units):
            impacts.append(Impact(
                input_category="physical",
                input_field="self_contained",
                input_value="All units self-contained ✓",
                impact_type=ImpactType.ENABLER,
                impact_score=25,
                headline="All units self-contained ✓",
                explanation=(
                    "All units have been verified as self-contained with their own "
                    "entrance, kitchen, and bathroom. This is ideal for title "
                    "splitting as each unit can be mortgaged and sold individually."
                ),
                required_actions=[],
                mitigation_options=[],
                framework_section="Section 1: Property Schedule"
            ))
    
    # Structural concerns
    if physical.structural_concerns:
        impacts.append(Impact(
            input_category="physical",
            input_field="structural_concerns",
            input_value=f"Structural issues: {', '.join(physical.structural_concerns[:3])}",
            impact_type=ImpactType.MAJOR_NEGATIVE,
            impact_score=-50,
            headline=f"Structural concerns identified",
            explanation=(
                f"Structural concerns have been identified: {', '.join(physical.structural_concerns)}. "
                f"These must be investigated by a structural engineer. Lenders will "
                f"require satisfactory reports before lending. Significant works "
                f"may be required."
            ),
            cost_impact=15000,  # Investigation + potential works
            time_impact_weeks=8,
            required_actions=[
                "Commission structural engineer report",
                "Obtain remedial works quotes",
                "Factor into purchase price negotiation"
            ],
            mitigation_options=[
                "Renegotiate price based on works required",
                "Request seller completes works",
                "Walk away if issues too severe"
            ],
            framework_section="Section 6: Risk Assessment"
        ))
    
    # Boundary issues
    if physical.boundary_issues:
        impacts.append(Impact(
            input_category="physical",
            input_field="boundary_issues",
            input_value=f"Boundary issues: {', '.join(physical.boundary_issues[:2])}",
            impact_type=ImpactType.MINOR_NEGATIVE,
            impact_score=-15,
            headline="Boundary issues identified",
            explanation=(
                f"Boundary issues have been identified: {', '.join(physical.boundary_issues)}. "
                f"These need resolution before title split as clear boundaries are "
                f"required for the Land Registry."
            ),
            cost_impact=1500,
            required_actions=[
                "Commission boundary survey",
                "Consider boundary agreement with neighbours",
                "Budget for Land Registry boundary determination if needed"
            ],
            mitigation_options=[
                "Agreed boundary (deed with neighbours)",
                "Land Registry determined boundary",
                "Title indemnity insurance"
            ],
            framework_section="Section 6: Risk Assessment - Boundary disputes"
        ))
    
    # Utilities
    if physical.utilities_separate is False:
        impacts.append(Impact(
            input_category="physical",
            input_field="utilities_separate",
            input_value="Utilities not separately metered",
            impact_type=ImpactType.MINOR_NEGATIVE,
            impact_score=-10,
            headline="Utilities not separately metered",
            explanation=(
                "The units do not have separate utility meters. While not a blocker, "
                "this creates complications for billing and is less attractive to "
                "buyers. Consider installing separate meters."
            ),
            cost_impact=2000,  # Meter separation
            required_actions=[
                "Obtain quotes for meter separation",
                "Factor into refurb budget"
            ],
            mitigation_options=[
                "Install separate meters",
                "Use included bills model"
            ],
            framework_section="Section 1: Property Schedule"
        ))
    
    return impacts
```

---


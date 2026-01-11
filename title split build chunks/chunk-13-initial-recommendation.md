## CHUNK 13: Initial Screening & Automated Recommendation

### 13.1 Automated Recommendation Engine

The system provides a recommendation at EVERY stage, starting with automated data only. As manual inputs are added, the recommendation updates.

```python
# src/analysis/recommendation.py

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class RecommendationLevel(str, Enum):
    STRONG_PROCEED = "strong_proceed"      # Score 85+, no blockers
    PROCEED = "proceed"                     # Score 70-84, minor concerns
    PROCEED_WITH_CAUTION = "proceed_caution"  # Score 60-69, needs DD
    REVIEW_REQUIRED = "review"              # Score 50-59, significant unknowns
    LIKELY_DECLINE = "likely_decline"       # Score 40-49, major concerns
    DECLINE = "decline"                     # Score <40 or hard blockers
    INSUFFICIENT_DATA = "insufficient"      # Cannot assess


class RecommendationStage(str, Enum):
    INITIAL = "initial"           # Scraped data only
    ENRICHED = "enriched"         # + EPC + comparables
    PARTIALLY_VERIFIED = "partial"  # Some manual inputs
    FULLY_VERIFIED = "verified"   # All critical inputs complete


class Recommendation(BaseModel):
    """Full recommendation with reasoning."""
    
    level: RecommendationLevel
    stage: RecommendationStage
    confidence: float  # 0-1, increases as more data added
    
    headline: str  # "Strong opportunity - proceed to title check"
    summary: str   # 2-3 sentence explanation
    
    # What's driving the recommendation
    positive_factors: list[str]
    negative_factors: list[str]
    unknown_factors: list[str]  # Items that need verification
    
    # Blockers (if any)
    hard_blockers: list[str]  # Deal-killers
    soft_blockers: list[str]  # Significant but potentially resolvable
    
    # Next steps
    required_actions: list[str]
    optional_actions: list[str]
    
    # Financial summary
    estimated_net_benefit: Optional[int]
    benefit_confidence: str  # low, medium, high
    
    # Risk level
    risk_level: str  # low, medium, high, very_high


def generate_initial_recommendation(
    property: Property,
    screening_result: ScreeningResult
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
            soft_blockers.append(f"{property.estimated_units} units may be too complex for small investor")
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
            negative.append(f"Higher entry at £{property.price_per_unit:,}/unit - margins tighter")
        else:
            soft_blockers.append(f"Premium pricing at £{property.price_per_unit:,}/unit - limited upside")
    
    # === CONDITION INDICATORS ===
    if property.refurb_indicators:
        positive.append("Refurbishment opportunity indicated - value-add potential")
    
    # === RED FLAGS FROM LISTING ===
    for flag in screening_result.red_flags:
        if flag.severity == "high":
            hard_blockers.append(flag.description)
        elif flag.severity == "medium":
            soft_blockers.append(flag.description)
        else:
            negative.append(flag.description)
    
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
    
    return Recommendation(
        level=level,
        stage=RecommendationStage.INITIAL,
        confidence=0.4,  # Low confidence at initial stage
        headline=headline,
        summary=_generate_summary(level, positive, negative, unknown),
        positive_factors=positive,
        negative_factors=negative,
        unknown_factors=unknown,
        hard_blockers=hard_blockers,
        soft_blockers=soft_blockers,
        required_actions=required_actions,
        optional_actions=optional_actions,
        estimated_net_benefit=None,  # Cannot estimate without enrichment
        benefit_confidence="none",
        risk_level="unknown"
    )
```

---


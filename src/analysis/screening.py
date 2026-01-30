from dataclasses import dataclass

from src.models.property import Property
from src.scrapers.extractors import RED_FLAGS


@dataclass
class ScreeningResult:
    passes: bool
    rejections: list[str]
    warnings: list[str]
    score: int  # 0-100 quick score


def initial_screen(property: Property) -> ScreeningResult:
    """
    Fast screening based on hard criteria.

    Returns screening result with pass/fail and reasons.
    Properties are only rejected for severe issues.
    Unknown/unclear data generates warnings, not rejections.
    """
    rejections = []
    warnings = []

    # Unit count - unknown is a warning, not a rejection
    if not property.estimated_units or property.estimated_units < 2:
        warnings.append("unit_count_unclear")
    elif property.estimated_units > 10:
        warnings.append("large_block")  # May still be viable

    # Tenure - only confirmed leasehold is a rejection
    if property.tenure == "leasehold":
        rejections.append("confirmed_leasehold")
    elif property.tenure == "share_of_freehold":
        warnings.append("share_of_freehold")  # Could still investigate

    # Price per unit sanity check - high price is warning, not rejection
    if property.price_per_unit:
        if property.price_per_unit > 200000:
            warnings.append("price_per_unit_high")
        elif property.price_per_unit < 20000:
            warnings.append("price_per_unit_suspicious")

    # Red flags from description
    description = (property.title or "") + " " + getattr(property, 'description', '')
    description_lower = description.lower()

    # Only severe structural/title issues cause rejection
    SEVERE_FLAGS = ["subsidence", "japanese knotweed", "flying freehold"]

    for flag_phrase, category in RED_FLAGS:
        if flag_phrase in description_lower:
            if flag_phrase in SEVERE_FLAGS:
                rejections.append(f"red_flag_{category}")
            else:
                warnings.append(f"warning_{category}")

    # Calculate quick score
    score = calculate_quick_score(property, rejections, warnings)

    return ScreeningResult(
        passes=len(rejections) == 0,
        rejections=rejections,
        warnings=warnings,
        score=score,
    )


def calculate_quick_score(
    property: Property,
    rejections: list[str],
    warnings: list[str],
) -> int:
    """Calculate a quick score without AI analysis."""
    if rejections:
        return 0

    score = 60  # Higher base score - most properties deserve investigation

    # Tenure bonus
    if property.tenure == "freehold":
        score += 15
        if property.tenure_confidence and property.tenure_confidence > 0.8:
            score += 5
    elif property.tenure == "unknown":
        score += 5  # Neutral - needs verification

    # Unit count bonus (sweet spot is 3-6 units)
    if property.estimated_units:
        if 3 <= property.estimated_units <= 6:
            score += 10
        elif 2 <= property.estimated_units <= 8:
            score += 5
        elif property.estimated_units > 8:
            score += 3  # Still potentially viable

    # Price per unit bonus
    if property.price_per_unit:
        if property.price_per_unit < 50000:
            score += 10
        elif property.price_per_unit < 75000:
            score += 5
        elif property.price_per_unit < 100000:
            score += 2

    # Deduct for warnings (less aggressive)
    score -= len(warnings) * 2

    return max(10, min(100, score))  # Minimum 10 for any passing property


def screen_batch(properties: list[Property]) -> list[tuple[Property, ScreeningResult]]:
    """Screen a batch of properties."""
    results = []
    for prop in properties:
        result = initial_screen(prop)
        results.append((prop, result))

    # Sort by score descending
    results.sort(key=lambda x: x[1].score, reverse=True)
    return results

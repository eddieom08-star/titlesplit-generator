from dataclasses import dataclass
from typing import Optional

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
    """
    rejections = []
    warnings = []

    # Must have estimated units
    if not property.estimated_units or property.estimated_units < 2:
        rejections.append("unit_count_unclear")

    if property.estimated_units and property.estimated_units > 10:
        rejections.append("too_many_units")

    # Must be freehold or unknown (not confirmed leasehold)
    if property.tenure == "leasehold":
        rejections.append("confirmed_leasehold")

    if property.tenure == "share_of_freehold":
        rejections.append("share_of_freehold")

    # Price per unit sanity check
    if property.price_per_unit:
        if property.price_per_unit > 150000:
            rejections.append("price_per_unit_too_high")
        if property.price_per_unit < 20000:
            warnings.append("price_per_unit_suspicious")

    # Red flags from description
    description = (property.title or "") + " " + getattr(property, 'description', '')
    description_lower = description.lower()

    for flag_phrase, category in RED_FLAGS:
        if flag_phrase in description_lower:
            if category in ["title_complexity", "condition_risk"]:
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

    score = 50  # Base score for passing basic screening

    # Tenure bonus
    if property.tenure == "freehold":
        score += 20
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

    # Price per unit bonus
    if property.price_per_unit:
        if property.price_per_unit < 50000:
            score += 10
        elif property.price_per_unit < 75000:
            score += 5

    # Deduct for warnings
    score -= len(warnings) * 3

    return max(0, min(100, score))


def screen_batch(properties: list[Property]) -> list[tuple[Property, ScreeningResult]]:
    """Screen a batch of properties."""
    results = []
    for prop in properties:
        result = initial_screen(prop)
        results.append((prop, result))

    # Sort by score descending
    results.sort(key=lambda x: x[1].score, reverse=True)
    return results

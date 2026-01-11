from typing import Optional

from src.models.property import Property
from src.analysis.ai_analysis import AIAnalysisResult
from src.data_sources.epc import EPCRecord, calculate_avg_epc_rating
from src.data_sources.land_registry import ComparableSale


def calculate_opportunity_score(
    property: Property,
    analysis: AIAnalysisResult,
    epcs: Optional[list[EPCRecord]] = None,
    comparables: Optional[list[ComparableSale]] = None,
) -> int:
    """
    Calculate composite opportunity score (0-100).

    Weighting based on Title Splitting Framework priorities:
    - Title/Tenure suitability: 30%
    - Financial upside: 25%
    - Condition/Refurb opportunity: 20%
    - Risk factors: 15%
    - Data confidence: 10%
    """
    epcs = epcs or []
    comparables = comparables or []
    score = 0

    # 1. Title/Tenure (30 points max)
    tenure_score = 0
    if analysis.tenure_analysis.likely_tenure == "freehold":
        tenure_score += 20
        if analysis.tenure_analysis.tenure_confidence > 0.8:
            tenure_score += 5
    elif analysis.tenure_analysis.likely_tenure == "unknown":
        tenure_score += 10  # Neutral - needs verification

    if analysis.tenure_analysis.single_title_likely:
        tenure_score += 5

    score += min(tenure_score, 30)

    # 2. Financial upside (25 points max)
    financial_score = 0
    uplift = analysis.financial_analysis.estimated_gross_uplift_percent
    if uplift:
        if uplift >= 30:
            financial_score = 25
        elif uplift >= 20:
            financial_score = 20
        elif uplift >= 15:
            financial_score = 15
        elif uplift >= 10:
            financial_score = 10
        elif uplift >= 5:
            financial_score = 5

    # Bonus for undervalued assessment
    if analysis.financial_analysis.price_assessment == "undervalued":
        financial_score += 5

    score += min(financial_score, 25)

    # 3. Condition/Refurb opportunity (20 points max)
    condition_score = 0
    if analysis.condition_analysis.refurb_needed:
        condition_score += 10
        if analysis.condition_analysis.refurb_scope in ["medium", "heavy"]:
            condition_score += 5
        elif analysis.condition_analysis.refurb_scope == "light":
            condition_score += 3

    if epcs:
        avg_rating, _ = calculate_avg_epc_rating(epcs)
        if avg_rating in ["E", "F", "G"]:
            condition_score += 5
        elif avg_rating == "D":
            condition_score += 3

    score += min(condition_score, 20)

    # 4. Risk factors (15 points max, start at 15 and deduct)
    risk_score = 15
    risk_score -= len(analysis.risk_analysis.red_flags) * 5
    risk_score -= len(analysis.risk_analysis.amber_flags) * 2

    # Deduct for blockers
    risk_score -= len(analysis.title_split_viability.blockers) * 3

    score += max(risk_score, 0)

    # 5. Data confidence (10 points max)
    confidence_score = 0
    if analysis.unit_analysis.unit_confidence > 0.8:
        confidence_score += 3
    elif analysis.unit_analysis.unit_confidence > 0.6:
        confidence_score += 1

    if analysis.tenure_analysis.tenure_confidence > 0.8:
        confidence_score += 3
    elif analysis.tenure_analysis.tenure_confidence > 0.6:
        confidence_score += 1

    estimated_units = property.estimated_units or analysis.unit_analysis.estimated_units
    if len(epcs) >= estimated_units:
        confidence_score += 2
    elif len(epcs) > 0:
        confidence_score += 1

    if len(comparables) >= 5:
        confidence_score += 2
    elif len(comparables) >= 3:
        confidence_score += 1

    score += min(confidence_score, 10)

    return min(score, 100)


def calculate_title_split_score(
    property: Property,
    analysis: AIAnalysisResult,
) -> int:
    """
    Calculate title split specific score (0-100).

    Focused on:
    - Single title likelihood
    - Self-contained units
    - Freehold status
    - Unit count sweet spot
    """
    score = 0

    # Freehold (40 points)
    if analysis.tenure_analysis.likely_tenure == "freehold":
        score += 30
        if analysis.tenure_analysis.tenure_confidence > 0.9:
            score += 10
        elif analysis.tenure_analysis.tenure_confidence > 0.7:
            score += 5

    # Single title (25 points)
    if analysis.tenure_analysis.single_title_likely:
        score += 20
        if "single" in analysis.tenure_analysis.single_title_evidence.lower():
            score += 5

    # Self-contained units (20 points)
    if analysis.unit_analysis.self_contained is True:
        score += 20
    elif analysis.unit_analysis.self_contained is None:
        score += 5  # Unknown - needs verification

    # Unit count sweet spot (15 points)
    units = analysis.unit_analysis.estimated_units
    if 3 <= units <= 6:
        score += 15
    elif 2 <= units <= 8:
        score += 10
    elif units > 1:
        score += 5

    return min(score, 100)


def get_recommendation_tier(
    opportunity_score: int,
    title_split_score: int,
    has_blockers: bool,
) -> str:
    """
    Get recommendation tier based on scores.

    Returns: 'A' (best), 'B', 'C', or 'D' (reject)
    """
    if has_blockers:
        return "D"

    combined = (opportunity_score * 0.6) + (title_split_score * 0.4)

    if combined >= 75:
        return "A"
    elif combined >= 55:
        return "B"
    elif combined >= 35:
        return "C"
    else:
        return "D"


def generate_score_breakdown(
    property: Property,
    analysis: AIAnalysisResult,
    epcs: Optional[list[EPCRecord]] = None,
    comparables: Optional[list[ComparableSale]] = None,
) -> dict:
    """Generate detailed score breakdown for transparency."""
    epcs = epcs or []
    comparables = comparables or []

    opportunity_score = calculate_opportunity_score(property, analysis, epcs, comparables)
    title_split_score = calculate_title_split_score(property, analysis)
    has_blockers = len(analysis.title_split_viability.blockers) > 0

    return {
        "opportunity_score": opportunity_score,
        "title_split_score": title_split_score,
        "recommendation_tier": get_recommendation_tier(
            opportunity_score, title_split_score, has_blockers
        ),
        "components": {
            "tenure": {
                "value": analysis.tenure_analysis.likely_tenure,
                "confidence": analysis.tenure_analysis.tenure_confidence,
                "single_title": analysis.tenure_analysis.single_title_likely,
            },
            "units": {
                "count": analysis.unit_analysis.estimated_units,
                "confidence": analysis.unit_analysis.unit_confidence,
                "self_contained": analysis.unit_analysis.self_contained,
            },
            "financial": {
                "price_per_unit": analysis.financial_analysis.price_per_unit,
                "assessment": analysis.financial_analysis.price_assessment,
                "uplift_percent": analysis.financial_analysis.estimated_gross_uplift_percent,
            },
            "condition": {
                "refurb_needed": analysis.condition_analysis.refurb_needed,
                "scope": analysis.condition_analysis.refurb_scope,
            },
            "risk": {
                "red_flags": analysis.risk_analysis.red_flags,
                "amber_flags": analysis.risk_analysis.amber_flags,
                "blockers": analysis.title_split_viability.blockers,
            },
            "data_quality": {
                "epc_count": len(epcs),
                "comparable_count": len(comparables),
            },
        },
    }

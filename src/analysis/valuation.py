from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from src.models.property import Property
from src.data_sources.epc import EPCRecord
from src.data_sources.land_registry import ComparableSale, calculate_time_adjusted_price


# Regional averages (£/sqft - update periodically)
REGIONAL_AVG_PER_SQFT = {
    "liverpool": 150,
    "manchester": 200,
    "leeds": 180,
    "sheffield": 160,
    "newcastle": 155,
    "wigan": 130,
    "bolton": 125,
    "bradford": 120,
    "hull": 110,
    "middlesbrough": 115,
}

# EPC condition adjustment factors
EPC_CONDITION_FACTORS = {
    "A": 1.05,
    "B": 1.03,
    "C": 1.00,
    "D": 0.97,
    "E": 0.94,
    "F": 0.90,
    "G": 0.85,
}


@dataclass
class UnitValuation:
    unit_address: str
    floor_area_sqm: Optional[float]
    floor_area_sqft: Optional[float]
    epc_rating: Optional[str]
    estimated_value: int
    value_low: int
    value_high: int
    confidence: str  # high, medium, low
    method: str
    comparable_count: int
    adjustments: dict


@dataclass
class BlockValuation:
    property_address: str
    asking_price: int
    num_units: int
    unit_valuations: list[UnitValuation]
    total_individual_value: int
    value_range_low: int
    value_range_high: int
    gross_uplift: int
    gross_uplift_percent: float
    avg_price_per_sqft: Optional[float]
    valuation_confidence: str
    methodology_notes: list[str]


def sqm_to_sqft(sqm: float) -> float:
    """Convert square meters to square feet."""
    return sqm * 10.764


def get_postcode_district(postcode: str) -> str:
    """Extract postcode district (e.g., 'L4' from 'L4 0TH')."""
    parts = postcode.upper().strip().split()
    if parts:
        return parts[0]
    return postcode[:2] if len(postcode) >= 2 else postcode


def filter_relevant_comparables(
    comparables: list[ComparableSale],
    postcode: str,
    max_age_days: int = 365,
) -> list[ComparableSale]:
    """Filter comparables to relevant ones for valuation."""
    postcode_district = get_postcode_district(postcode)
    cutoff_date = datetime.now() - timedelta(days=max_age_days)

    return [
        c for c in comparables
        if c.property_type == "F"  # Flats only
        and c.postcode.upper().startswith(postcode_district)
        and c.sale_date > cutoff_date
        and not c.new_build  # Exclude new builds
    ]


def calculate_avg_price_per_sqft(
    comparables: list[ComparableSale],
    epcs: Optional[list[EPCRecord]] = None,
) -> Optional[float]:
    """Calculate average price per sqft from comparables."""
    samples = []

    for comp in comparables:
        if hasattr(comp, 'floor_area_sqm') and comp.floor_area_sqm and comp.floor_area_sqm > 0:
            sqft = sqm_to_sqft(comp.floor_area_sqm)
            # Time-adjust the price
            adjusted_price = calculate_time_adjusted_price(comp.price, comp.sale_date)
            samples.append(adjusted_price / sqft)

    if samples:
        return sum(samples) / len(samples)
    return None


def estimate_unit_value(
    epc: EPCRecord,
    avg_price_per_sqft: float,
    confidence: str = "medium",
) -> UnitValuation:
    """Estimate value for a single unit based on comparables."""
    floor_area_sqft = sqm_to_sqft(epc.floor_area) if epc.floor_area else None

    if floor_area_sqft:
        base_value = floor_area_sqft * avg_price_per_sqft

        # Apply condition adjustment
        condition_factor = EPC_CONDITION_FACTORS.get(epc.current_rating, 1.0)
        adjusted_value = int(base_value * condition_factor)

        # Calculate range (±10% for medium confidence, ±15% for low)
        variance = 0.10 if confidence in ["high", "medium"] else 0.15
        value_low = int(adjusted_value * (1 - variance))
        value_high = int(adjusted_value * (1 + variance))

        adjustments = {
            "base_value": int(base_value),
            "epc_adjustment": round((condition_factor - 1) * 100, 1),
        }
    else:
        # Fallback to assumed average size
        assumed_sqft = 500  # ~46 sqm
        adjusted_value = int(assumed_sqft * avg_price_per_sqft)
        value_low = int(adjusted_value * 0.85)
        value_high = int(adjusted_value * 1.15)
        floor_area_sqft = assumed_sqft
        adjustments = {"note": "Assumed average floor area"}
        confidence = "low"

    return UnitValuation(
        unit_address=epc.address,
        floor_area_sqm=epc.floor_area,
        floor_area_sqft=floor_area_sqft,
        epc_rating=epc.current_rating,
        estimated_value=adjusted_value,
        value_low=value_low,
        value_high=value_high,
        confidence=confidence,
        method="comparable_analysis",
        comparable_count=0,  # Will be set by caller
        adjustments=adjustments,
    )


def estimate_values_rule_of_thumb(
    property: Property,
    epcs: list[EPCRecord],
) -> list[UnitValuation]:
    """
    Fallback valuation when insufficient comparables.

    Uses regional average £/sqft.
    """
    city = (property.city or "liverpool").lower()
    avg_sqft = REGIONAL_AVG_PER_SQFT.get(city, 150)

    valuations = []
    for epc in epcs:
        if epc.floor_area and epc.floor_area > 0:
            sqft = sqm_to_sqft(epc.floor_area)
            base_value = int(sqft * avg_sqft)
        else:
            # Assume average flat size of 50 sqm
            sqft = sqm_to_sqft(50)
            base_value = int(sqft * avg_sqft)

        # Apply minimal condition adjustment
        factor = EPC_CONDITION_FACTORS.get(epc.current_rating, 1.0)
        adjusted_value = int(base_value * factor)

        valuations.append(UnitValuation(
            unit_address=epc.address,
            floor_area_sqm=epc.floor_area,
            floor_area_sqft=sqft,
            epc_rating=epc.current_rating,
            estimated_value=adjusted_value,
            value_low=int(adjusted_value * 0.80),
            value_high=int(adjusted_value * 1.20),
            confidence="low",
            method="regional_average",
            comparable_count=0,
            adjustments={"regional_avg_sqft": avg_sqft},
        ))

    return valuations


async def estimate_individual_unit_values(
    property: Property,
    epcs: list[EPCRecord],
    comparables: list[ComparableSale],
) -> list[UnitValuation]:
    """
    Estimate individual unit values using comparables.

    Methodology:
    1. Filter relevant flat sales in same postcode district
    2. Calculate average £/sqft from comparables
    3. Apply floor area and EPC condition adjustments
    """
    # Filter relevant comparables
    relevant_comps = filter_relevant_comparables(
        comparables,
        property.postcode,
        max_age_days=365,
    )

    # Need minimum comparables for reliable estimate
    if len(relevant_comps) < 3:
        return estimate_values_rule_of_thumb(property, epcs)

    # Calculate average price per sqft
    avg_price_per_sqft = calculate_avg_price_per_sqft(relevant_comps, epcs)

    if not avg_price_per_sqft:
        # Fallback to regional average
        city = (property.city or "liverpool").lower()
        avg_price_per_sqft = REGIONAL_AVG_PER_SQFT.get(city, 150)

    # Determine confidence based on comparable count
    if len(relevant_comps) >= 10:
        confidence = "high"
    elif len(relevant_comps) >= 5:
        confidence = "medium"
    else:
        confidence = "low"

    # Estimate each unit
    valuations = []
    for epc in epcs:
        valuation = estimate_unit_value(epc, avg_price_per_sqft, confidence)
        valuation.comparable_count = len(relevant_comps)
        valuations.append(valuation)

    return valuations


async def create_block_valuation(
    property: Property,
    epcs: list[EPCRecord],
    comparables: list[ComparableSale],
) -> BlockValuation:
    """Create complete block valuation with all units."""
    unit_valuations = await estimate_individual_unit_values(property, epcs, comparables)

    # Aggregate values
    total_value = sum(v.estimated_value for v in unit_valuations)
    total_low = sum(v.value_low for v in unit_valuations)
    total_high = sum(v.value_high for v in unit_valuations)

    # Calculate uplift
    gross_uplift = total_value - property.asking_price
    gross_uplift_percent = round((gross_uplift / property.asking_price) * 100, 1) if property.asking_price else 0

    # Calculate avg price per sqft
    total_sqft = sum(v.floor_area_sqft or 0 for v in unit_valuations)
    avg_price_per_sqft = total_value / total_sqft if total_sqft > 0 else None

    # Determine overall confidence
    confidences = [v.confidence for v in unit_valuations]
    if all(c == "high" for c in confidences):
        overall_confidence = "high"
    elif all(c == "low" for c in confidences):
        overall_confidence = "low"
    else:
        overall_confidence = "medium"

    # Methodology notes
    notes = []
    methods = set(v.method for v in unit_valuations)
    if "comparable_analysis" in methods:
        comp_count = unit_valuations[0].comparable_count if unit_valuations else 0
        notes.append(f"Based on {comp_count} comparable sales in area")
    if "regional_average" in methods:
        notes.append("Used regional average £/sqft due to limited comparables")

    return BlockValuation(
        property_address=f"{property.address_line1}, {property.postcode}",
        asking_price=property.asking_price,
        num_units=len(unit_valuations),
        unit_valuations=unit_valuations,
        total_individual_value=total_value,
        value_range_low=total_low,
        value_range_high=total_high,
        gross_uplift=gross_uplift,
        gross_uplift_percent=gross_uplift_percent,
        avg_price_per_sqft=avg_price_per_sqft,
        valuation_confidence=overall_confidence,
        methodology_notes=notes,
    )

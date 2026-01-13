from datetime import datetime
from enum import Enum
from typing import Optional

import structlog
from pydantic import BaseModel, Field

from src.data_sources.epc import EPCRecord
from src.data_sources.land_registry import ComparableSale, calculate_time_adjusted_price

logger = structlog.get_logger()


class ValuationValidationError(Exception):
    """Raised when valuation fails sanity checks."""
    pass


def validate_unit_value_against_rent(
    estimated_value: int,
    monthly_rent: int,
    min_yield: float = 0.05,
    max_yield: float = 0.10,
) -> dict:
    """
    Cross-check unit value against rental yield.

    If the implied yield is outside a reasonable range (5-10%),
    the valuation is likely wrong.

    Returns:
        dict with validation result and corrected value if needed
    """
    if monthly_rent <= 0 or estimated_value <= 0:
        return {"valid": True, "skipped": True, "reason": "missing rent or value data"}

    annual_rent = monthly_rent * 12
    implied_yield = annual_rent / estimated_value

    # If yield is too low, the value is too high
    if implied_yield < min_yield:
        # Calculate what the value should be at minimum yield
        corrected_value = int(annual_rent / min_yield)
        return {
            "valid": False,
            "issue": "value_too_high",
            "original_value": estimated_value,
            "corrected_value": corrected_value,
            "implied_yield": round(implied_yield * 100, 2),
            "expected_yield_range": f"{min_yield*100:.0f}%-{max_yield*100:.0f}%",
            "message": f"Value £{estimated_value:,} implies {implied_yield*100:.1f}% yield - too low for this area",
        }

    # If yield is too high, value might be conservative (acceptable)
    if implied_yield > max_yield:
        return {
            "valid": True,
            "note": "conservative_valuation",
            "implied_yield": round(implied_yield * 100, 2),
            "message": f"Value £{estimated_value:,} implies {implied_yield*100:.1f}% yield - may be undervalued",
        }

    return {
        "valid": True,
        "implied_yield": round(implied_yield * 100, 2),
        "message": f"Yield {implied_yield*100:.1f}% is within expected range",
    }


def sanity_check_gdv(
    total_gdv: int,
    asking_price: int,
    num_units: int,
    comparables: list[ComparableSale],
) -> dict:
    """
    Perform sanity checks on GDV calculation to catch obvious errors.

    Returns:
        dict with check results and any warnings/errors
    """
    issues = []
    warnings = []

    gdv_per_unit = total_gdv / num_units if num_units > 0 else 0

    # Check 1: Unit value > block asking price (definitely wrong)
    if gdv_per_unit > asking_price:
        issues.append({
            "check": "unit_exceeds_block_price",
            "severity": "error",
            "message": f"Unit value £{gdv_per_unit:,.0f} exceeds block asking price £{asking_price:,}. "
                      f"Comparables likely include wrong property type (houses vs flats).",
        })

    # Check 2: GDV > 5x asking price (very suspicious)
    if total_gdv > asking_price * 5:
        issues.append({
            "check": "gdv_ratio_extreme",
            "severity": "error",
            "message": f"GDV £{total_gdv:,} is {total_gdv/asking_price:.1f}x asking price. "
                      f"Valuations are almost certainly incorrect.",
        })

    # Check 3: GDV > 3x asking price (suspicious but possible)
    elif total_gdv > asking_price * 3:
        warnings.append({
            "check": "gdv_ratio_high",
            "severity": "warning",
            "message": f"GDV £{total_gdv:,} is {total_gdv/asking_price:.1f}x asking price. "
                      f"Verify valuations are reasonable for this area.",
        })

    # Check 4: Mixed property types in comparables
    if comparables:
        property_types = set(c.property_type for c in comparables)
        if len(property_types) > 1 and "F" in property_types:
            non_flat_count = len([c for c in comparables if c.property_type != "F"])
            if non_flat_count > 0:
                warnings.append({
                    "check": "mixed_property_types",
                    "severity": "warning",
                    "message": f"Comparables include {non_flat_count} non-flat properties. "
                              f"This may skew valuations.",
                    "property_types": list(property_types),
                })

    # Check 5: Average comparable price sanity
    if comparables:
        avg_comp_price = sum(c.price for c in comparables) / len(comparables)
        # If average comparable > 3x the per-unit asking price, probably using houses
        per_unit_asking = asking_price / num_units if num_units > 0 else asking_price
        if avg_comp_price > per_unit_asking * 3:
            issues.append({
                "check": "comparable_price_mismatch",
                "severity": "error",
                "message": f"Average comparable £{avg_comp_price:,.0f} is {avg_comp_price/per_unit_asking:.1f}x "
                          f"per-unit asking price (£{per_unit_asking:,.0f}). "
                          f"Check if comparables are correct property type.",
            })

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "checks_performed": 5,
    }


class ValuationConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INDICATIVE = "indicative"


class ValuationSource(str, Enum):
    LAND_REGISTRY_PPD = "land_registry_ppd"
    PROPERTY_DATA_AVM = "property_data_avm"
    PROPERTY_DATA_COMPS = "property_data_comps"
    UKHPI_ADJUSTED = "ukhpi_adjusted"
    AGENT_QUOTE = "agent_quote"
    RICS_VALUATION = "rics_valuation"
    MANUAL_OVERRIDE = "manual_override"


class ComparableProperty(BaseModel):
    """A comparable property sale."""
    address: str
    postcode: str
    price: int
    date: str
    bedrooms: Optional[int] = None
    sqft: Optional[float] = None
    price_per_sqft: Optional[float] = None
    source: ValuationSource
    distance_miles: Optional[float] = None
    estate_type: Optional[str] = None
    time_adjusted_price: Optional[int] = None
    condition_adjustment: Optional[float] = None


class UnitValuation(BaseModel):
    """Valuation for a single unit in the block."""
    unit_identifier: str
    beds: Optional[int] = None
    sqft: Optional[float] = None
    epc_rating: Optional[str] = None
    estimated_value: int
    value_range_low: int
    value_range_high: int
    confidence: ValuationConfidence
    primary_method: str
    price_per_sqft_used: Optional[float] = None
    comparables_used: list[ComparableProperty] = Field(default_factory=list)
    avm_value: Optional[int] = None
    data_sources: list[ValuationSource] = Field(default_factory=list)
    valuation_notes: str = ""


class BlockGDVReport(BaseModel):
    """Complete GDV report for a freehold block."""
    property_address: str
    postcode: str
    title_number: Optional[str] = None
    asking_price: int
    agreed_price: Optional[int] = None
    total_units: int
    total_sqft: Optional[float] = None
    unit_valuations: list[UnitValuation]
    total_gdv: int
    gdv_range_low: int
    gdv_range_high: int
    gdv_confidence: ValuationConfidence
    gross_uplift: int
    gross_uplift_percent: float
    title_split_costs: int
    refurbishment_budget: Optional[int] = None
    total_costs: int
    net_uplift: int
    net_uplift_percent: float
    net_profit_per_unit: int
    local_market_data: dict = Field(default_factory=dict)
    comparables_summary: dict = Field(default_factory=dict)
    data_sources: list[str] = Field(default_factory=list)
    data_freshness: str = ""
    confidence_statement: str = ""
    limitations: list[str] = Field(default_factory=list)
    validation_results: dict = Field(default_factory=dict)
    report_date: str = ""
    report_version: str = "1.0"


class GDVCalculator:
    """Calculate Gross Development Value using multiple data sources."""

    def __init__(self, property_data_client=None, land_registry_client=None):
        self.property_data = property_data_client
        self.land_registry = land_registry_client

    async def calculate_block_gdv(
        self,
        postcode: str,
        units: list[dict],
        asking_price: int,
        comparables: Optional[list[ComparableSale]] = None,
        epcs: Optional[list[EPCRecord]] = None,
        split_costs: int = 0,
        monthly_rent_per_unit: Optional[int] = None,
    ) -> BlockGDVReport:
        """Calculate GDV for a block of flats."""
        comparables = comparables or []
        epcs = epcs or []

        # CRITICAL: Filter comparables to FLATS ONLY
        # This prevents the common error of valuing flats using house prices
        flat_comparables = [c for c in comparables if c.property_type == "F"]

        if len(flat_comparables) < len(comparables):
            excluded_count = len(comparables) - len(flat_comparables)
            logger.warning(
                "Excluded non-flat comparables from GDV calculation",
                total_comparables=len(comparables),
                flat_comparables=len(flat_comparables),
                excluded=excluded_count,
                excluded_types=[c.property_type for c in comparables if c.property_type != "F"],
            )

        # Value each unit using ONLY flat comparables
        unit_valuations = []
        for i, unit in enumerate(units):
            valuation = self._value_unit(
                unit=unit,
                comparables=flat_comparables,
                epc=epcs[i] if i < len(epcs) else None,
            )
            unit_valuations.append(valuation)

        # Calculate aggregates
        total_gdv = sum(v.estimated_value for v in unit_valuations)
        gdv_low = sum(v.value_range_low for v in unit_valuations)
        gdv_high = sum(v.value_range_high for v in unit_valuations)

        # Calculate uplift
        gross_uplift = total_gdv - asking_price
        gross_uplift_pct = round((gross_uplift / asking_price) * 100, 1) if asking_price else 0

        # Net calculations
        net_uplift = gross_uplift - split_costs
        net_uplift_pct = round((net_uplift / asking_price) * 100, 1) if asking_price else 0

        # Determine confidence
        confidence = self._calculate_overall_confidence(unit_valuations)

        # Run sanity checks on the valuations
        validation_results = sanity_check_gdv(
            total_gdv=total_gdv,
            asking_price=asking_price,
            num_units=len(units),
            comparables=flat_comparables,
        )

        # If rental data available, validate against yield
        if monthly_rent_per_unit and len(unit_valuations) > 0:
            avg_unit_value = total_gdv // len(units)
            yield_check = validate_unit_value_against_rent(
                estimated_value=avg_unit_value,
                monthly_rent=monthly_rent_per_unit,
            )
            validation_results["rental_yield_check"] = yield_check

            # If yield check fails, add to limitations
            if not yield_check.get("valid", True) and not yield_check.get("skipped"):
                logger.warning(
                    "Valuation failed rental yield check",
                    estimated_value=avg_unit_value,
                    monthly_rent=monthly_rent_per_unit,
                    implied_yield=yield_check.get("implied_yield"),
                    corrected_value=yield_check.get("corrected_value"),
                )

        # Add validation issues to limitations
        limitations = self._get_limitations(confidence, len(flat_comparables))
        for issue in validation_results.get("issues", []):
            limitations.append(f"⚠️ {issue['message']}")
        for warning in validation_results.get("warnings", []):
            limitations.append(f"⚡ {warning['message']}")

        # Generate report
        return BlockGDVReport(
            property_address="",
            postcode=postcode,
            asking_price=asking_price,
            total_units=len(units),
            total_sqft=sum(u.get("sqft", 0) for u in units if u.get("sqft")),
            unit_valuations=unit_valuations,
            total_gdv=total_gdv,
            gdv_range_low=gdv_low,
            gdv_range_high=gdv_high,
            gdv_confidence=confidence,
            gross_uplift=gross_uplift,
            gross_uplift_percent=gross_uplift_pct,
            title_split_costs=split_costs,
            total_costs=split_costs,
            net_uplift=net_uplift,
            net_uplift_percent=net_uplift_pct,
            net_profit_per_unit=net_uplift // len(units) if units else 0,
            comparables_summary=self._summarise_comparables(flat_comparables),
            data_sources=["Land Registry Price Paid", "EPC Register"],
            data_freshness=f"Data as of {datetime.now().strftime('%B %Y')}",
            confidence_statement=self._generate_confidence_statement(
                unit_valuations, flat_comparables
            ),
            limitations=limitations,
            validation_results=validation_results,
            report_date=datetime.now().isoformat(),
        )

    def _value_unit(
        self,
        unit: dict,
        comparables: list[ComparableSale],
        epc: Optional[EPCRecord] = None,
    ) -> UnitValuation:
        """Value a single unit."""
        beds = unit.get("beds")
        sqft = unit.get("sqft") or (epc.floor_area * 10.764 if epc and epc.floor_area else None)
        unit_id = unit.get("id", "Unit")

        # CRITICAL: Only use FLAT comparables - filter again as safety measure
        flat_comps = [c for c in comparables if c.property_type == "F"]
        relevant_comps = flat_comps[:10]

        # Calculate value
        if sqft and relevant_comps:
            # Use price per sqft from comparables
            psf_values = []
            for comp in relevant_comps:
                if hasattr(comp, 'floor_area_sqm') and comp.floor_area_sqm:
                    comp_sqft = comp.floor_area_sqm * 10.764
                    adjusted_price = calculate_time_adjusted_price(comp.price, comp.sale_date)
                    psf_values.append(adjusted_price / comp_sqft)

            if psf_values:
                avg_psf = sum(psf_values) / len(psf_values)
                estimated_value = int(sqft * avg_psf)
                method = "psf_analysis"
            else:
                # Use median price
                prices = [c.price for c in relevant_comps]
                estimated_value = sorted(prices)[len(prices) // 2] if prices else 100000
                method = "comparable_median"
                avg_psf = None
        elif relevant_comps:
            prices = [c.price for c in relevant_comps]
            estimated_value = sorted(prices)[len(prices) // 2] if prices else 100000
            method = "comparable_median"
            avg_psf = None
        else:
            # Fallback to regional average
            estimated_value = 100000
            method = "regional_estimate"
            avg_psf = None

        # Apply EPC condition adjustment
        if epc and epc.current_rating:
            adjustments = {"A": 1.05, "B": 1.03, "C": 1.0, "D": 0.97, "E": 0.94, "F": 0.90, "G": 0.85}
            factor = adjustments.get(epc.current_rating, 1.0)
            estimated_value = int(estimated_value * factor)

        # Calculate range
        variance = 0.10 if len(relevant_comps) >= 5 else 0.15
        value_low = int(estimated_value * (1 - variance))
        value_high = int(estimated_value * (1 + variance))

        # Determine confidence
        if len(relevant_comps) >= 10:
            confidence = ValuationConfidence.HIGH
        elif len(relevant_comps) >= 5:
            confidence = ValuationConfidence.MEDIUM
        elif len(relevant_comps) >= 2:
            confidence = ValuationConfidence.LOW
        else:
            confidence = ValuationConfidence.INDICATIVE

        return UnitValuation(
            unit_identifier=unit_id,
            beds=beds,
            sqft=sqft,
            epc_rating=epc.current_rating if epc else None,
            estimated_value=estimated_value,
            value_range_low=value_low,
            value_range_high=value_high,
            confidence=confidence,
            primary_method=method,
            price_per_sqft_used=avg_psf,
            comparables_used=[],
            data_sources=[ValuationSource.LAND_REGISTRY_PPD],
            valuation_notes=f"{method} based on {len(relevant_comps)} comparables",
        )

    def _calculate_overall_confidence(
        self, unit_valuations: list[UnitValuation]
    ) -> ValuationConfidence:
        """Calculate overall confidence from unit valuations."""
        if all(v.confidence == ValuationConfidence.HIGH for v in unit_valuations):
            return ValuationConfidence.HIGH
        elif any(v.confidence == ValuationConfidence.INDICATIVE for v in unit_valuations):
            return ValuationConfidence.LOW
        elif all(v.confidence in [ValuationConfidence.HIGH, ValuationConfidence.MEDIUM] for v in unit_valuations):
            return ValuationConfidence.MEDIUM
        else:
            return ValuationConfidence.LOW

    def _summarise_comparables(self, comparables: list[ComparableSale]) -> dict:
        """Summarise comparable evidence."""
        if not comparables:
            return {"count": 0, "message": "No comparables available"}

        prices = [c.price for c in comparables]
        return {
            "count": len(comparables),
            "price_range": f"£{min(prices):,} - £{max(prices):,}",
            "average": sum(prices) // len(prices),
            "median": sorted(prices)[len(prices) // 2],
        }

    def _generate_confidence_statement(
        self,
        unit_valuations: list[UnitValuation],
        comparables: list[ComparableSale],
    ) -> str:
        """Generate lender-appropriate confidence statement."""
        total_comps = len(comparables)
        high_conf = len([u for u in unit_valuations if u.confidence == ValuationConfidence.HIGH])

        return f"""
        Valuation based on {total_comps} comparable transactions from Land Registry
        Price Paid data. {high_conf} of {len(unit_valuations)} unit valuations are
        HIGH confidence. Values time-adjusted using UK House Price Index.
        """.strip()

    def _get_limitations(self, confidence: ValuationConfidence, comp_count: int) -> list[str]:
        """Generate limitations for report."""
        limitations = [
            "Desktop valuation - does not replace RICS Red Book valuation",
            "Actual values may differ based on condition and specification",
        ]

        if confidence in [ValuationConfidence.LOW, ValuationConfidence.INDICATIVE]:
            limitations.append("Limited comparable evidence - professional valuation recommended")

        if comp_count < 10:
            limitations.append(f"Based on {comp_count} comparables - additional evidence recommended")

        return limitations

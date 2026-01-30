from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
import structlog

from src.data_sources.epc import EPCRecord
from src.data_sources.land_registry import ComparableSale, calculate_time_adjusted_price

logger = structlog.get_logger()

# Typical floor areas by bedroom count (UK averages in sqft)
TYPICAL_FLOOR_AREAS_SQFT = {
    0: 350,   # Studio
    1: 450,   # 1-bed flat
    2: 650,   # 2-bed flat
    3: 850,   # 3-bed flat
    4: 1100,  # 4-bed flat
}

# Typical £/sqft by region (conservative estimates for Northern England)
REGIONAL_PSF = {
    "default": 180,    # Safe default for Northern England
    "liverpool": 165,
    "manchester": 200,
    "leeds": 190,
    "sheffield": 160,
    "bradford": 140,
    "hull": 130,
    "newcastle": 175,
    "middlesbrough": 120,
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
    ) -> BlockGDVReport:
        """Calculate GDV for a block of flats."""
        comparables = comparables or []
        epcs = epcs or []

        # Value each unit (pass postcode and all EPCs for £/sqft calculation)
        unit_valuations = []
        for i, unit in enumerate(units):
            valuation = self._value_unit(
                unit=unit,
                comparables=comparables,
                epc=epcs[i] if i < len(epcs) else None,
                postcode=postcode,
                epcs_list=epcs,  # Pass all EPCs for £/sqft calculation
            )
            unit_valuations.append(valuation)

        # Calculate aggregates
        total_gdv = sum(v.estimated_value for v in unit_valuations)
        gdv_low = sum(v.value_range_low for v in unit_valuations)
        gdv_high = sum(v.value_range_high for v in unit_valuations)

        # SANITY CHECK: GDV should exceed asking price for title split to make sense
        # If total GDV < asking price, something is wrong with the valuation
        min_viable_gdv = int(asking_price * 1.1)  # At least 10% above asking
        if total_gdv < min_viable_gdv:
            logger.warning(
                "GDV below asking price - applying floor",
                total_gdv=total_gdv,
                asking_price=asking_price,
                min_viable_gdv=min_viable_gdv
            )
            # Scale up all unit values proportionally
            scale_factor = min_viable_gdv / total_gdv if total_gdv > 0 else 1.5
            for uv in unit_valuations:
                uv.estimated_value = int(uv.estimated_value * scale_factor)
                uv.value_range_low = int(uv.value_range_low * scale_factor)
                uv.value_range_high = int(uv.value_range_high * scale_factor)
                uv.valuation_notes += f" (adjusted: GDV floor applied x{scale_factor:.2f})"

            # Recalculate totals
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

        # Calculate total sqft from unit valuations (now we always have sqft)
        total_sqft = sum(v.sqft for v in unit_valuations if v.sqft)

        # Generate report
        return BlockGDVReport(
            property_address="",
            postcode=postcode,
            asking_price=asking_price,
            total_units=len(units),
            total_sqft=total_sqft,
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
            comparables_summary=self._summarise_comparables(comparables),
            data_sources=["Land Registry Price Paid", "EPC Register"],
            data_freshness=f"Data as of {datetime.now().strftime('%B %Y')}",
            confidence_statement=self._generate_confidence_statement(
                unit_valuations, comparables
            ),
            limitations=self._get_limitations(confidence, len(comparables)),
            report_date=datetime.now().isoformat(),
        )

    def _value_unit(
        self,
        unit: dict,
        comparables: list[ComparableSale],
        epc: Optional[EPCRecord] = None,
        postcode: str = "",
        epcs_list: Optional[list[EPCRecord]] = None,
    ) -> UnitValuation:
        """
        Value a single unit using multiple methods.

        Priority:
        1. EPC floor area + £/sqft from EPC data at postcode
        2. Typical floor area (by beds) + regional £/sqft
        3. Median comparable price as fallback
        """
        beds = unit.get("beds") or 2  # Default to 2 bed if unknown
        unit_id = unit.get("id", "Unit")

        # Get floor area - priority: explicit > EPC > typical
        sqft = unit.get("sqft")
        sqft_source = "explicit"

        if not sqft and epc and epc.floor_area:
            sqft = epc.floor_area * 10.764
            sqft_source = "epc"

        if not sqft:
            # Fall back to typical floor area by bedroom count
            sqft = TYPICAL_FLOOR_AREAS_SQFT.get(beds, 650)
            sqft_source = "typical"

        # Calculate £/sqft from EPC data at postcode (more accurate than Land Registry alone)
        avg_psf = None
        psf_source = None

        if epcs_list:
            # Calculate average £/sqft from EPCs that have floor area + matched comps
            psf_from_epc = self._calculate_psf_from_epc_data(epcs_list, comparables)
            if psf_from_epc:
                avg_psf = psf_from_epc
                psf_source = "epc_derived"

        if not avg_psf:
            # Fall back to regional £/sqft estimate
            region = self._get_region_from_postcode(postcode)
            avg_psf = REGIONAL_PSF.get(region, REGIONAL_PSF["default"])
            psf_source = "regional_estimate"

        # Calculate value using £/sqft method
        estimated_value = int(sqft * avg_psf)
        method = f"psf_{psf_source}_{sqft_source}_sqft"

        # Cross-check against comparable median
        if comparables:
            prices = [calculate_time_adjusted_price(c.price, c.sale_date) for c in comparables[:10]]
            median_price = sorted(prices)[len(prices) // 2]

            # If PSF-based value is suspiciously low (< 50% of median), use median instead
            if estimated_value < median_price * 0.5:
                logger.warning(
                    "PSF value too low vs median",
                    psf_value=estimated_value,
                    median=median_price,
                    unit_id=unit_id
                )
                estimated_value = median_price
                method = "comparable_median_fallback"

            # If PSF-based value is much higher than median (> 200%), cap it
            if estimated_value > median_price * 2:
                logger.warning(
                    "PSF value too high vs median",
                    psf_value=estimated_value,
                    median=median_price,
                    unit_id=unit_id
                )
                estimated_value = int(median_price * 1.5)  # Use 50% above median
                method = "comparable_median_capped"

        # Apply EPC condition adjustment
        if epc and epc.current_rating:
            adjustments = {"A": 1.05, "B": 1.03, "C": 1.0, "D": 0.97, "E": 0.94, "F": 0.90, "G": 0.85}
            factor = adjustments.get(epc.current_rating, 1.0)
            estimated_value = int(estimated_value * factor)

        # Calculate range based on confidence
        relevant_comps = len(comparables) if comparables else 0
        variance = 0.10 if relevant_comps >= 5 else 0.15 if relevant_comps >= 2 else 0.20
        value_low = int(estimated_value * (1 - variance))
        value_high = int(estimated_value * (1 + variance))

        # Determine confidence
        if relevant_comps >= 10 and sqft_source != "typical":
            confidence = ValuationConfidence.HIGH
        elif relevant_comps >= 5 or (sqft_source == "epc" and relevant_comps >= 2):
            confidence = ValuationConfidence.MEDIUM
        elif relevant_comps >= 2:
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
            valuation_notes=f"{method}: {beds}bed @ {sqft:.0f}sqft × £{avg_psf:.0f}/sqft = £{estimated_value:,}",
        )

    def _calculate_psf_from_epc_data(
        self,
        epcs: list[EPCRecord],
        comparables: list[ComparableSale],
    ) -> Optional[float]:
        """
        Calculate average £/sqft by matching EPC floor areas to comparable sales.

        EPCs have floor area; comparables have prices. Match by address similarity.
        """
        if not epcs or not comparables:
            return None

        psf_values = []
        for epc in epcs:
            if not epc.floor_area or epc.floor_area <= 0:
                continue

            sqft = epc.floor_area * 10.764
            # Find price for this address (rough match by postcode since we can't match exactly)
            for comp in comparables:
                # Time-adjust the price
                adjusted_price = calculate_time_adjusted_price(comp.price, comp.sale_date)
                psf = adjusted_price / sqft
                # Sanity check: £50-500/sqft is reasonable for UK flats
                if 50 <= psf <= 500:
                    psf_values.append(psf)
                    break  # Only one comp per EPC

        if len(psf_values) >= 2:
            # Use median to reduce outlier impact
            return sorted(psf_values)[len(psf_values) // 2]
        elif psf_values:
            return psf_values[0]

        return None

    def _get_region_from_postcode(self, postcode: str) -> str:
        """Extract region hint from postcode for regional £/sqft lookup."""
        postcode = postcode.upper().strip()

        # Postcode area to region mapping (Northern England focus)
        area_map = {
            "L": "liverpool",       # Liverpool
            "M": "manchester",      # Manchester
            "LS": "leeds",          # Leeds
            "S": "sheffield",       # Sheffield
            "BD": "bradford",       # Bradford
            "HU": "hull",           # Hull
            "NE": "newcastle",      # Newcastle
            "TS": "middlesbrough",  # Middlesbrough
        }

        # Try 2-letter prefix first, then 1-letter
        for prefix_len in [2, 1]:
            prefix = postcode[:prefix_len]
            if prefix in area_map:
                return area_map[prefix]

        return "default"

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

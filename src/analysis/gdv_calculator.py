from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.data_sources.epc import EPCRecord
from src.data_sources.land_registry import ComparableSale, calculate_time_adjusted_price


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

        # Value each unit
        unit_valuations = []
        for i, unit in enumerate(units):
            valuation = self._value_unit(
                unit=unit,
                comparables=comparables,
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
    ) -> UnitValuation:
        """Value a single unit."""
        beds = unit.get("beds")
        sqft = unit.get("sqft") or (epc.floor_area * 10.764 if epc and epc.floor_area else None)
        unit_id = unit.get("id", "Unit")

        # Filter comparables
        relevant_comps = comparables[:10]

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

## CHUNK 19: Lender-Grade GDV Calculation Engine

### 19.1 GDV Calculation Methodology

For lender presentations, the GDV (Gross Development Value) must be calculated using **defensible market evidence**. This section implements a multi-source validation approach.

```python
# src/analysis/gdv_calculator.py

from typing import List, Optional
from pydantic import BaseModel
from decimal import Decimal
from enum import Enum


class ValuationConfidence(str, Enum):
    HIGH = "high"        # 10+ comps, tight range, multiple sources agree
    MEDIUM = "medium"    # 5-10 comps, reasonable range
    LOW = "low"          # <5 comps, wide range, limited data
    INDICATIVE = "indicative"  # Insufficient data, estimate only


class ValuationSource(str, Enum):
    LAND_REGISTRY_PPD = "land_registry_ppd"  # Actual transactions
    PROPERTY_DATA_AVM = "property_data_avm"  # PropertyData valuation
    PROPERTY_DATA_COMPS = "property_data_comps"  # PropertyData comparables
    UKHPI_ADJUSTED = "ukhpi_adjusted"  # HPI-adjusted historic sale
    AGENT_QUOTE = "agent_quote"  # Estate agent market appraisal
    RICS_VALUATION = "rics_valuation"  # Red Book valuation
    MANUAL_OVERRIDE = "manual_override"  # User-provided value


class ComparableProperty(BaseModel):
    """A comparable property sale."""
    address: str
    postcode: str
    price: int
    date: str
    bedrooms: Optional[int]
    sqft: Optional[float]
    price_per_sqft: Optional[float]
    source: ValuationSource
    distance_miles: Optional[float]
    estate_type: Optional[str]  # F=Freehold, L=Leasehold
    
    # Adjustments
    time_adjusted_price: Optional[int] = None  # HPI adjusted to today
    condition_adjustment: Optional[float] = None  # % adjustment for condition


class UnitValuation(BaseModel):
    """Valuation for a single unit in the block."""
    
    unit_identifier: str  # "Flat 1", "Ground Floor" etc.
    
    # Unit characteristics
    beds: Optional[int]
    sqft: Optional[float]
    epc_rating: Optional[str]
    
    # Primary valuation
    estimated_value: int
    value_range_low: int
    value_range_high: int
    confidence: ValuationConfidence
    
    # Valuation methodology
    primary_method: str  # "comparable", "psf", "avm"
    price_per_sqft_used: Optional[float]
    
    # Supporting evidence
    comparables_used: List[ComparableProperty]
    avm_value: Optional[int]  # PropertyData AVM
    
    # Source attribution
    data_sources: List[ValuationSource]
    
    # Notes for lender
    valuation_notes: str


class BlockGDVReport(BaseModel):
    """
    Complete GDV report for a freehold block.
    
    This is the primary output for lender presentations.
    """
    
    # Property identification
    property_address: str
    postcode: str
    title_number: Optional[str]
    
    # Current position
    asking_price: int
    agreed_price: Optional[int]  # If offer made
    
    # Block summary
    total_units: int
    total_sqft: Optional[float]
    
    # Unit-by-unit valuations
    unit_valuations: List[UnitValuation]
    
    # Aggregate GDV
    total_gdv: int
    gdv_range_low: int
    gdv_range_high: int
    gdv_confidence: ValuationConfidence
    
    # Uplift calculation
    gross_uplift: int
    gross_uplift_percent: float
    
    # Costs (from cost calculator)
    title_split_costs: int
    refurbishment_budget: Optional[int]
    total_costs: int
    
    # Net position
    net_uplift: int
    net_uplift_percent: float
    net_profit_per_unit: int
    
    # Market context
    local_market_data: dict  # HPI, yields, trends
    
    # Comparable evidence summary
    comparables_summary: dict
    
    # Data sources used
    data_sources: List[str]
    data_freshness: str  # "Data as of January 2026"
    
    # Confidence statement
    confidence_statement: str
    limitations: List[str]
    
    # Report metadata
    report_date: str
    report_version: str


class GDVCalculator:
    """
    Calculate Gross Development Value using multiple data sources.
    
    Methodology:
    1. Gather comparables from Land Registry PPD (actual transactions)
    2. Validate with PropertyData AVM
    3. Cross-check with £/sqft analysis
    4. Apply time adjustments using UKHPI
    5. Calculate confidence based on data quality
    6. Generate lender-ready report
    """
    
    def __init__(
        self,
        property_data_client,
        land_registry_client,
    ):
        self.property_data = property_data_client
        self.land_registry = land_registry_client
    
    async def calculate_block_gdv(
        self,
        postcode: str,
        units: List[dict],  # [{"id": "Flat 1", "beds": 2, "sqft": 650}, ...]
        asking_price: int,
    ) -> BlockGDVReport:
        """
        Calculate GDV for a block of flats.
        
        This is the main entry point for GDV calculation.
        """
        
        # 1. Gather market data
        market_data = await self._gather_market_data(postcode)
        
        # 2. Get comparable sales
        comparables = await self._get_comparables(
            postcode=postcode,
            property_type="flat"
        )
        
        # 3. Value each unit
        unit_valuations = []
        for unit in units:
            valuation = await self._value_unit(
                postcode=postcode,
                unit=unit,
                comparables=comparables,
                market_data=market_data
            )
            unit_valuations.append(valuation)
        
        # 4. Calculate aggregate GDV
        total_gdv = sum(v.estimated_value for v in unit_valuations)
        gdv_low = sum(v.value_range_low for v in unit_valuations)
        gdv_high = sum(v.value_range_high for v in unit_valuations)
        
        # 5. Calculate uplift
        gross_uplift = total_gdv - asking_price
        gross_uplift_percent = round((gross_uplift / asking_price) * 100, 1)
        
        # 6. Determine overall confidence
        confidence = self._calculate_overall_confidence(unit_valuations)
        
        # 7. Generate confidence statement
        confidence_statement = self._generate_confidence_statement(
            unit_valuations=unit_valuations,
            comparables=comparables,
            market_data=market_data
        )
        
        return BlockGDVReport(
            property_address="",  # Fill from property data
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
            gross_uplift_percent=gross_uplift_percent,
            title_split_costs=0,  # Calculate separately
            refurbishment_budget=None,
            total_costs=0,
            net_uplift=gross_uplift,  # Adjust when costs added
            net_uplift_percent=gross_uplift_percent,
            net_profit_per_unit=gross_uplift // len(units),
            local_market_data=market_data,
            comparables_summary=self._summarise_comparables(comparables),
            data_sources=["Land Registry Price Paid", "PropertyData AVM", "UK HPI"],
            data_freshness=f"Data as of {datetime.now().strftime('%B %Y')}",
            confidence_statement=confidence_statement,
            limitations=self._get_limitations(confidence, comparables),
            report_date=datetime.now().isoformat(),
            report_version="1.0"
        )
    
    async def _gather_market_data(self, postcode: str) -> dict:
        """Gather local market context data."""
        
        # Get data from multiple sources
        yields = await self.property_data.get_yields(postcode)
        growth = await self.property_data.get_price_growth(postcode)
        
        # Get regional HPI
        # Extract region from postcode (simplified)
        region = self._postcode_to_region(postcode)
        hpi_data = await self.land_registry.get_regional_hpi(region)
        
        return {
            "gross_yield": yields.get("yield"),
            "average_rent_pcm": yields.get("average_rent_pcm"),
            "price_growth_1y": growth.get("1_year"),
            "price_growth_5y": growth.get("5_year"),
            "regional_hpi": hpi_data[0] if hpi_data else None,
            "regional_average_price": hpi_data[0].get("avgPrice") if hpi_data else None,
        }
    
    async def _get_comparables(
        self,
        postcode: str,
        property_type: str = "flat",
    ) -> List[ComparableProperty]:
        """
        Get comparable sales from multiple sources.
        
        Priority:
        1. Land Registry PPD (actual transactions)
        2. PropertyData comparables
        """
        
        comparables = []
        
        # Get from Land Registry (primary source)
        postcode_district = postcode.split()[0]
        lr_comps = await self.land_registry.get_price_paid_comparables(
            postcode_district=postcode_district,
            property_type="F",  # Flats
            months_back=18
        )
        
        for comp in lr_comps:
            comparables.append(ComparableProperty(
                address=comp["address"],
                postcode=comp["postcode"],
                price=comp["price"],
                date=comp["date"],
                source=ValuationSource.LAND_REGISTRY_PPD,
                estate_type=comp.get("estate_type"),
                bedrooms=None,  # Not in PPD
                sqft=None,  # Need to match with EPC
                price_per_sqft=None,
            ))
        
        # Get from PropertyData (adds bedrooms, sqft)
        pd_comps = await self.property_data.get_sold_prices(
            postcode=postcode,
            property_type=property_type,
            max_age=18
        )
        
        for comp in pd_comps.get("data", []):
            comparables.append(ComparableProperty(
                address=comp["address"],
                postcode=postcode,
                price=comp["price"],
                date=comp["date"],
                source=ValuationSource.PROPERTY_DATA_COMPS,
                bedrooms=comp.get("bedrooms"),
                sqft=comp.get("sqft"),
                price_per_sqft=comp.get("price_per_sqft"),
                estate_type=None,
            ))
        
        # Deduplicate (prefer PropertyData as has more detail)
        comparables = self._deduplicate_comparables(comparables)
        
        # Time-adjust prices to current date
        comparables = await self._time_adjust_comparables(comparables)
        
        return comparables
    
    async def _value_unit(
        self,
        postcode: str,
        unit: dict,
        comparables: List[ComparableProperty],
        market_data: dict,
    ) -> UnitValuation:
        """
        Value a single unit using multiple methods.
        
        Methods:
        1. Comparable analysis (primary if sufficient comps)
        2. £/sqft calculation (if sqft known)
        3. AVM fallback (PropertyData)
        """
        
        beds = unit.get("beds")
        sqft = unit.get("sqft")
        unit_id = unit.get("id", "Unknown")
        
        # Filter comparables by bedroom count
        relevant_comps = [
            c for c in comparables
            if c.bedrooms == beds or c.bedrooms is None
        ][:10]  # Top 10
        
        # Method 1: Comparable-based valuation
        comp_value = None
        if len(relevant_comps) >= 3:
            # Use median of time-adjusted prices
            prices = [c.time_adjusted_price or c.price for c in relevant_comps]
            comp_value = sorted(prices)[len(prices) // 2]  # Median
        
        # Method 2: £/sqft calculation
        psf_value = None
        psf_used = None
        if sqft:
            psf_data = await self.property_data.get_sold_prices_per_sqft(
                postcode=postcode,
                property_type="flat",
                bedrooms=beds
            )
            if psf_data.get("average"):
                psf_used = psf_data["average"]
                psf_value = int(sqft * psf_used)
        
        # Method 3: AVM fallback
        avm_value = None
        try:
            avm_result = await self.property_data.get_valuation(
                postcode=postcode,
                property_type="flat",
                bedrooms=beds,
                internal_area=int(sqft) if sqft else None,
            )
            avm_value = avm_result.get("result_int")
        except:
            pass
        
        # Determine primary value
        if comp_value and psf_value:
            # Average of methods if both available
            estimated_value = (comp_value + psf_value) // 2
            primary_method = "comparable + psf"
        elif comp_value:
            estimated_value = comp_value
            primary_method = "comparable"
        elif psf_value:
            estimated_value = psf_value
            primary_method = "psf"
        elif avm_value:
            estimated_value = avm_value
            primary_method = "avm"
        else:
            # Last resort: use regional average
            estimated_value = int(market_data.get("regional_average_price", 100000))
            primary_method = "regional_average"
        
        # Calculate range (±10% for medium confidence)
        range_factor = 0.10
        value_low = int(estimated_value * (1 - range_factor))
        value_high = int(estimated_value * (1 + range_factor))
        
        # Determine confidence
        confidence = self._determine_unit_confidence(
            comp_count=len(relevant_comps),
            methods_used=[m for m in [comp_value, psf_value, avm_value] if m],
            values_agree=self._values_agree([comp_value, psf_value, avm_value])
        )
        
        # Data sources used
        sources = [ValuationSource.LAND_REGISTRY_PPD]
        if avm_value:
            sources.append(ValuationSource.PROPERTY_DATA_AVM)
        
        return UnitValuation(
            unit_identifier=unit_id,
            beds=beds,
            sqft=sqft,
            epc_rating=unit.get("epc"),
            estimated_value=estimated_value,
            value_range_low=value_low,
            value_range_high=value_high,
            confidence=confidence,
            primary_method=primary_method,
            price_per_sqft_used=psf_used,
            comparables_used=relevant_comps[:5],  # Top 5 for report
            avm_value=avm_value,
            data_sources=sources,
            valuation_notes=self._generate_unit_notes(
                beds, sqft, primary_method, confidence, len(relevant_comps)
            )
        )
    
    def _determine_unit_confidence(
        self,
        comp_count: int,
        methods_used: List,
        values_agree: bool,
    ) -> ValuationConfidence:
        """Determine confidence level for a unit valuation."""
        
        if comp_count >= 10 and len(methods_used) >= 2 and values_agree:
            return ValuationConfidence.HIGH
        elif comp_count >= 5 and len(methods_used) >= 1:
            return ValuationConfidence.MEDIUM
        elif comp_count >= 2:
            return ValuationConfidence.LOW
        else:
            return ValuationConfidence.INDICATIVE
    
    def _values_agree(self, values: List[Optional[int]]) -> bool:
        """Check if multiple valuation methods agree (within 15%)."""
        valid_values = [v for v in values if v]
        if len(valid_values) < 2:
            return True  # Can't disagree with one value
        
        avg = sum(valid_values) / len(valid_values)
        return all(abs(v - avg) / avg < 0.15 for v in valid_values)
    
    def _generate_confidence_statement(
        self,
        unit_valuations: List[UnitValuation],
        comparables: List[ComparableProperty],
        market_data: dict,
    ) -> str:
        """Generate a lender-appropriate confidence statement."""
        
        total_comps = len(comparables)
        lr_comps = len([c for c in comparables if c.source == ValuationSource.LAND_REGISTRY_PPD])
        
        high_confidence_units = len([u for u in unit_valuations if u.confidence == ValuationConfidence.HIGH])
        
        statement = f"""
        Valuation Methodology & Confidence:
        
        This GDV assessment is based on {total_comps} comparable transactions,
        including {lr_comps} verified Land Registry Price Paid records from the 
        past 18 months. Values have been time-adjusted using the UK House Price 
        Index to reflect current market conditions.
        
        {high_confidence_units} of {len(unit_valuations)} unit valuations are 
        assessed as HIGH confidence based on comparable evidence depth.
        
        Local market context: {market_data.get('price_growth_1y', 'N/A')}% price 
        growth over 12 months, {market_data.get('gross_yield', 'N/A')}% gross yield.
        
        Data sources: HM Land Registry Price Paid Data, PropertyData.co.uk AVM,
        UK House Price Index, EPC Register.
        """
        
        return statement.strip()
    
    def _get_limitations(
        self,
        confidence: ValuationConfidence,
        comparables: List[ComparableProperty]
    ) -> List[str]:
        """Generate list of limitations for the report."""
        
        limitations = [
            "This is a desktop valuation and does not replace a RICS Red Book valuation",
            "Actual values may differ based on property condition and specification",
            "Market conditions may change between report date and transaction",
        ]
        
        if confidence in [ValuationConfidence.LOW, ValuationConfidence.INDICATIVE]:
            limitations.append(
                "Limited comparable evidence available - recommend professional valuation"
            )
        
        if len(comparables) < 10:
            limitations.append(
                f"Valuation based on {len(comparables)} comparables - additional evidence recommended"
            )
        
        return limitations
```

---


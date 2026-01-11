## CHUNK 8: Individual Unit Valuation

### 8.1 Comparable-Based Valuation

```python
# src/analysis/valuation.py

async def estimate_individual_unit_values(
    property: Property,
    epcs: list[EPCRecord],
    comparables: list[Comparable]
) -> list[dict]:
    """
    Estimate individual unit values using comparables.
    
    Methodology:
    1. Get recent flat sales in same postcode district
    2. Adjust for beds, sqft, condition
    3. Apply location and market adjustments
    """
    unit_values = []
    
    # Get postcode district (e.g., "L4" from "L4 0TH")
    postcode_district = property.postcode.split()[0]
    
    # Filter relevant comparables
    relevant_comps = [
        c for c in comparables
        if c.property_type == "flat"
        and c.postcode.startswith(postcode_district)
        and c.sale_date > datetime.now() - timedelta(days=365)
    ]
    
    if not relevant_comps:
        # Fall back to rule of thumb
        return estimate_values_rule_of_thumb(property, epcs)
    
    # Calculate £/sqft from comps
    price_per_sqft_samples = []
    for comp in relevant_comps:
        if comp.floor_area:
            price_per_sqft_samples.append(comp.price / comp.floor_area)
    
    avg_price_per_sqft = sum(price_per_sqft_samples) / len(price_per_sqft_samples)
    
    # Estimate each unit
    for epc in epcs:
        if epc.floor_area:
            base_value = epc.floor_area * avg_price_per_sqft
            
            # Condition adjustment (EPC-based)
            condition_factor = {
                "A": 1.05, "B": 1.03, "C": 1.0,
                "D": 0.97, "E": 0.94, "F": 0.90, "G": 0.85
            }.get(epc.current_rating, 1.0)
            
            adjusted_value = int(base_value * condition_factor)
            
            unit_values.append({
                "unit": epc.address,
                "sqft": epc.floor_area,
                "epc": epc.current_rating,
                "estimated_value": adjusted_value,
                "confidence": "medium" if len(relevant_comps) >= 5 else "low",
            })
    
    return unit_values


def estimate_values_rule_of_thumb(
    property: Property,
    epcs: list[EPCRecord]
) -> list[dict]:
    """
    Fallback valuation when insufficient comparables.
    
    Uses regional average £/sqft or price multipliers.
    """
    # Regional averages (update periodically)
    REGIONAL_AVG_PER_SQFT = {
        "liverpool": 150,
        "manchester": 200,
        "leeds": 180,
        "sheffield": 160,
        "newcastle": 155,
        "wigan": 130,
        "bolton": 125,
        "bradford": 120,
    }
    
    city = property.city.lower() if property.city else "liverpool"
    avg_sqft = REGIONAL_AVG_PER_SQFT.get(city, 150)
    
    unit_values = []
    for epc in epcs:
        if epc.floor_area:
            value = int(epc.floor_area * avg_sqft)
        else:
            # Assume average flat size of 50 sqm
            value = int(50 * 10.764 * avg_sqft)  # sqm to sqft
        
        unit_values.append({
            "unit": epc.address,
            "estimated_value": value,
            "confidence": "low",
            "method": "regional_average",
        })
    
    return unit_values
```

---


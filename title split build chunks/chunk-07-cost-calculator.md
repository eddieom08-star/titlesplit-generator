## CHUNK 7: Cost-Benefit Calculator

### 7.1 Transaction Costs Model

**Based on Framework Section 5:**

```python
# src/analysis/costs.py

# Cost model (per property unless noted)
COST_MODEL = {
    # Legal costs
    "solicitor_per_unit": {
        "min": 300,
        "max": 600,
        "typical": 450,
    },
    
    # Land Registry fees (based on value bands)
    "land_registry_fees": {
        # Value-based fee scale (current as of 2024)
        "bands": [
            (0, 80000, 20),
            (80001, 100000, 40),
            (100001, 200000, 95),
            (200001, 500000, 135),
            (500001, 1000000, 270),
            (1000001, float('inf'), 455),
        ]
    },
    
    # Title plan preparation
    "title_plan_per_unit": {
        "min": 100,
        "max": 300,
        "typical": 200,
    },
    
    # Lender costs (one-off)
    "lender_consent_fee": {
        "min": 500,
        "max": 2500,
        "typical": 1000,
    },
    "lender_legal_costs": {
        "min": 500,
        "max": 2000,
        "typical": 1000,
    },
    
    # Valuations
    "valuation_per_unit": {
        "min": 150,
        "max": 350,
        "typical": 250,
    },
    
    # Insurance
    "insurance_endorsement_per_unit": {
        "min": 50,
        "max": 100,
        "typical": 75,
    },
    
    # Contingency
    "contingency_percent": 10,
}

def estimate_split_costs(
    num_units: int,
    individual_values: list[int]
) -> dict:
    """
    Estimate total title splitting costs.
    
    Returns detailed breakdown per Framework Section 5.
    """
    costs = {}
    
    # Per-unit costs
    costs["solicitor_fees"] = num_units * COST_MODEL["solicitor_per_unit"]["typical"]
    costs["title_plans"] = num_units * COST_MODEL["title_plan_per_unit"]["typical"]
    costs["valuations"] = num_units * COST_MODEL["valuation_per_unit"]["typical"]
    costs["insurance"] = num_units * COST_MODEL["insurance_endorsement_per_unit"]["typical"]
    
    # Land Registry fees (per unit based on value)
    lr_fees = 0
    for value in individual_values:
        for min_val, max_val, fee in COST_MODEL["land_registry_fees"]["bands"]:
            if min_val <= value <= max_val:
                lr_fees += fee
                break
    costs["land_registry"] = lr_fees
    
    # One-off costs
    costs["lender_consent"] = COST_MODEL["lender_consent_fee"]["typical"]
    costs["lender_legal"] = COST_MODEL["lender_legal_costs"]["typical"]
    
    # Subtotal
    subtotal = sum(costs.values())
    
    # Contingency
    costs["contingency"] = int(subtotal * COST_MODEL["contingency_percent"] / 100)
    
    # Total
    costs["total"] = subtotal + costs["contingency"]
    costs["per_unit"] = costs["total"] // num_units
    
    return costs
```

### 7.2 Benefit Calculator

```python
# src/analysis/benefits.py

def estimate_split_benefits(
    asking_price: int,
    num_units: int,
    individual_values: list[int],
    split_costs: dict
) -> dict:
    """
    Calculate expected benefits from title split.
    
    Based on Framework Section 5 and Go/No-Go criteria.
    """
    benefits = {}
    
    # Aggregate individual values
    aggregate_value = sum(individual_values)
    
    # Gross uplift
    benefits["current_portfolio_value"] = asking_price
    benefits["individual_values_aggregate"] = aggregate_value
    benefits["gross_uplift"] = aggregate_value - asking_price
    benefits["gross_uplift_percent"] = round(
        (benefits["gross_uplift"] / asking_price) * 100, 1
    )
    
    # Net uplift (after costs)
    benefits["transaction_costs"] = split_costs["total"]
    benefits["net_uplift"] = benefits["gross_uplift"] - benefits["transaction_costs"]
    benefits["net_uplift_percent"] = round(
        (benefits["net_uplift"] / asking_price) * 100, 1
    )
    
    # Per unit metrics
    benefits["net_benefit_per_unit"] = benefits["net_uplift"] // num_units
    
    # Framework Go/No-Go thresholds
    benefits["meets_threshold"] = benefits["net_benefit_per_unit"] >= 2000
    benefits["cost_ratio"] = round(
        (benefits["transaction_costs"] / asking_price) * 100, 1
    )
    benefits["cost_ratio_acceptable"] = benefits["cost_ratio"] <= 3.0
    
    return benefits
```

---


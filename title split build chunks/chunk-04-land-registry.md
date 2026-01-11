## CHUNK 4: Data Enrichment - Land Registry Integration

### 4.1 Price Paid API

**Data Source:** HM Land Registry Price Paid Data
**Endpoint:** `https://landregistry.data.gov.uk/data/ppi/transaction-record.json`
**Authentication:** None required
**Rate Limit:** Reasonable use
**Documentation:** https://landregistry.data.gov.uk/

```python
# src/enrichment/land_registry.py

async def get_comparable_sales(
    postcode: str,
    property_type: str = "F",  # F=Flat, T=Terraced, S=Semi, D=Detached
    months_back: int = 24
) -> list[ComparableSale]:
    """
    Fetch recent sales in the area for valuation.
    
    Used for:
    - Section 5: Individual unit values (aggregate vs portfolio)
    - Section 2: Exit strategy (market evidence)
    """
    pass
```

**Price Paid Data Points:**

| Field | Framework Mapping | Use |
|-------|------------------|-----|
| `transactionPrice` | Section 5: Valuation | Comparable pricing |
| `transactionDate` | Section 5: Valuation | Recency weighting |
| `propertyType` | Section 5: Valuation | Match to property type |
| `newBuild` | Section 5: Valuation | Exclude new builds from comps |
| `estateType` | Section 1: Tenure | F=Freehold, L=Leasehold |

### 4.2 Title Investigation (Manual/Paid)

**⚠️ IMPORTANT: Full title data requires manual lookup or paid service**

**Data Source Options:**

1. **HM Land Registry Portal** (£3 per title)
   - URL: https://www.gov.uk/search-property-information-land-registry
   - Requires: Manual lookup, property address
   - Returns: Title number, registered owner, charges, restrictions

2. **Commercial Providers** (API access, volume pricing)
   - SearchFlow, InfoTrack, TM Group
   - Typical cost: £8-15 per title
   - Returns: Full title register, title plan

**For MVP: Mark as "Title Verification Required" - manual step**

```python
# Fields that CANNOT be automatically obtained:
MANUAL_VERIFICATION_REQUIRED = [
    "title_number",           # Land Registry lookup required
    "registered_proprietor",  # Land Registry lookup required
    "existing_charges",       # Land Registry lookup required
    "restrictive_covenants",  # Land Registry lookup required
    "easements",              # Land Registry lookup required
    "title_plan",             # Land Registry lookup required
]
```

---


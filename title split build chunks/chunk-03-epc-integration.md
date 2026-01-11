## CHUNK 3: Data Enrichment - EPC API Integration

### 3.1 EPC API Client

**Data Source:** UK EPC Open Data API
**Endpoint:** `https://epc.opendatacommunities.org/api/v1/domestic/search`
**Authentication:** Free registration required (email + API key, base64 encoded)
**Rate Limit:** 5000 requests/day
**Documentation:** https://epc.opendatacommunities.org/docs/api/domestic

```python
# src/enrichment/epc.py

async def get_epcs_for_postcode(postcode: str) -> list[EPCRecord]:
    """
    Fetch all EPC certificates at a postcode.
    
    This is the PRIMARY method for:
    1. Confirming unit count (count distinct addresses)
    2. Assessing refurbishment need (low ratings = opportunity)
    3. Estimating property age
    4. Calculating floor areas
    """
    pass

async def match_epcs_to_property(
    postcode: str,
    address_hint: str
) -> list[EPCRecord]:
    """
    Match EPCs to a specific building.
    
    Strategy:
    1. Fetch all EPCs at postcode
    2. Filter by address similarity (fuzzy match)
    3. Deduplicate (keep latest per unit)
    4. Return matched records
    """
    pass
```

**EPC Data Points Used:**

| EPC Field | Framework Mapping | Use |
|-----------|------------------|-----|
| `current-energy-rating` | Section 1: Property condition | Refurb indicator (D/E/F/G = opportunity) |
| `potential-energy-rating` | Section 5: Benefit calculation | Uplift potential |
| `total-floor-area` | Section 5: Valuation | Value per sqft calculation |
| `property-type` | Section 1: Property Schedule | Confirm flat vs house |
| `built-form` | Section 1: Property type | Detached/semi/terrace/flat |
| `construction-age-band` | Section 6: Risk assessment | Older = more issues |
| `transaction-type` | N/A | Indicates if rental vs owner-occupied |
| `lodgement-date` | Data quality | More recent = more reliable |

**EPC-Based Unit Count Validation:**

```python
def validate_unit_count_from_epcs(
    epcs: list[EPCRecord],
    claimed_units: int
) -> tuple[int, float]:
    """
    Cross-validate unit count from EPC records.
    
    Returns: (validated_count, confidence_score)
    
    Logic:
    - If EPC count matches claimed: confidence 0.95
    - If EPC count > claimed: use EPC count, confidence 0.90
    - If EPC count < claimed: flag for review, confidence 0.60
    - If no EPCs found: retain claimed, confidence 0.50
    """
    # Count unique unit addresses
    unique_units = set()
    for epc in epcs:
        # Normalise address (Flat 1 vs Flat 1A vs 1 etc)
        normalised = normalise_unit_address(epc.address)
        unique_units.add(normalised)
    
    epc_count = len(unique_units)
    
    if epc_count == claimed_units:
        return claimed_units, 0.95
    elif epc_count > claimed_units:
        return epc_count, 0.90
    elif epc_count > 0:
        return claimed_units, 0.60  # Discrepancy - needs review
    else:
        return claimed_units, 0.50  # No EPC data
```

---


## CHUNK 5: Data Enrichment - Planning Data

### 5.1 Planning History

**Data Source:** Local Authority Planning Portals (no unified API)
**Reality Check:** Each council has different systems, most require scraping

**Practical Approach for MVP:**

```python
# src/enrichment/planning.py

# Planning portal URLs by council
PLANNING_PORTALS = {
    "liverpool": "https://planningandbuildingcontrol.liverpool.gov.uk/",
    "manchester": "https://pa.manchester.gov.uk/online-applications/",
    "wigan": "https://planning.wigan.gov.uk/online-applications/",
    # ... etc
}

async def get_planning_portal_url(postcode: str) -> str:
    """
    Return the planning portal URL for manual lookup.
    
    For MVP, we generate a search URL - user clicks to investigate.
    Full automation would require per-council scraper development.
    """
    council = postcode_to_council(postcode)
    base_url = PLANNING_PORTALS.get(council)
    if base_url:
        return f"{base_url}?searchType=address&postcode={postcode}"
    return None
```

**Framework Requirements vs Reality:**

| Framework Requirement | Auto Available? | Alternative |
|----------------------|-----------------|-------------|
| Current use class | ❌ No | Infer from listing description |
| Planning history | ❌ No | Provide portal link for manual check |
| Planning restrictions | ❌ No | Flag if "Article 4" in listing |
| HMO licensing status | ❌ No | Council lookup required |
| Building regs compliance | ❌ No | Manual verification |

---


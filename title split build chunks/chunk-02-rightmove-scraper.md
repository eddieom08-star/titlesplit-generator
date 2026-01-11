## CHUNK 2: Data Ingestion - Scraper Implementation

### 2.1 Rightmove Scraper

**Data Source:** Rightmove Hidden REST API
**Endpoint:** `https://www.rightmove.co.uk/api/_search`
**Rate Limit:** 2 seconds between requests
**Daily Limit:** ~1000 requests recommended

```python
# src/scrapers/rightmove.py

# Search parameters for title split opportunities
SEARCH_CONFIGS = [
    {
        "keywords": ["block of flats", "freehold"],
        "property_type": "flat",
        "min_price": 100000,
        "max_price": 800000,
    },
    {
        "keywords": ["investment opportunity", "freehold"],
        "property_type": "flat",
    },
    {
        "keywords": ["refurbishment", "flats"],
        "property_type": "flat",
    },
]

# Target locations (with pre-resolved location IDs)
LOCATIONS = {
    "liverpool": "REGION^786",
    "manchester": "REGION^904",
    "wigan": "REGION^1290",
    "leeds": "REGION^711",
    "sheffield": "REGION^1138",
    "bradford": "REGION^181",
    "newcastle": "REGION^1852",
    "bolton": "REGION^167",
    "hull": "REGION^594",
    "middlesbrough": "REGION^933",
}
```

**Data Extracted from Rightmove:**

| Field | Source | Reliability |
|-------|--------|-------------|
| `asking_price` | `price.amount` | ✅ High |
| `address` | `displayAddress` | ✅ High |
| `postcode` | Regex from address | ⚠️ Medium |
| `latitude/longitude` | `location` object | ✅ High |
| `description` | `summary` (search) or full page | ✅ High |
| `images` | `propertyImages` array | ✅ High |
| `agent_name` | `customer.branchDisplayName` | ✅ High |
| `tenure` | Text extraction from description | ⚠️ Medium |
| `estimated_units` | Text extraction from description | ⚠️ Medium |
| `listed_date` | `listingUpdate.listingUpdateDate` | ⚠️ Medium |

### 2.2 Text Extraction Patterns

```python
# src/scrapers/extractors.py

# Unit count extraction patterns (ordered by reliability)
UNIT_COUNT_PATTERNS = [
    # Explicit statements
    (r'block of (\d+) (?:self[- ]?contained )?(?:flats|apartments)', 0.95),
    (r'(\d+) (?:self[- ]?contained )?(?:flats|apartments|units)', 0.90),
    (r'comprises (\d+)', 0.85),
    (r'containing (\d+)', 0.85),
    
    # Bedroom-based inference
    (r'(\d+) x \d[- ]?bed', 0.80),  # "4 x 2-bed flats"
    (r'(\d+) \d[- ]?bedroom flats', 0.80),
    
    # Weaker patterns
    (r'(\d+)[- ]?storey', 0.60),  # May indicate units
]

# Tenure extraction patterns
TENURE_PATTERNS = {
    'freehold': [
        (r'\bfreehold\b(?! flat)', 0.95),  # "freehold" but not "freehold flat"
        (r'freehold block', 0.98),
        (r'all\s+(?:flats?\s+)?freehold', 0.95),
        (r'sold freehold', 0.90),
    ],
    'leasehold': [
        (r'\bleasehold\b', 0.95),
        (r'remaining (?:on )?lease', 0.90),
        (r'\d+ years? (?:remaining|left)', 0.85),
    ],
    'share_of_freehold': [
        (r'share of (?:the )?freehold', 0.98),
        (r'sof\b', 0.70),
    ],
}

# Refurbishment indicators
REFURB_INDICATORS = [
    ('needs modernisation', 0.9),
    ('refurbishment required', 0.95),
    ('refurbishment opportunity', 0.95),
    ('in need of updating', 0.85),
    ('requires updating', 0.85),
    ('renovation project', 0.90),
    ('development opportunity', 0.80),
    ('cash buyers only', 0.75),  # Often indicates issues
    ('probate', 0.70),
    ('deceased estate', 0.70),
]

# Red flags (negative indicators)
RED_FLAGS = [
    ('flying freehold', 'title_complexity'),
    ('share of freehold', 'not_single_title'),
    ('commercial', 'mixed_use_complexity'),
    ('retail', 'mixed_use_complexity'),
    ('shop', 'mixed_use_complexity'),
    ('ground rent', 'leasehold_indicator'),
    ('service charge', 'leasehold_indicator'),
    ('management company', 'leasehold_indicator'),
    ('structural issues', 'condition_risk'),
    ('subsidence', 'condition_risk'),
    ('japanese knotweed', 'condition_risk'),
]
```

---


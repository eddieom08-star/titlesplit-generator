## CHUNK 1: Project Setup & Core Data Models

### 1.1 Technology Stack

```
Backend: Python 3.11+ with FastAPI
Database: PostgreSQL 16
Task Queue: Celery + Redis (for background scraping)
AI: Claude API (for text analysis)
Frontend: Next.js 14 (React)
Deployment: Docker + Railway/Render
```

### 1.2 Core Data Models

Create these SQLAlchemy models in `src/models/`:

```python
# Property - the main entity
class Property:
    id: UUID
    source: str  # rightmove, zoopla, auction
    source_id: str
    source_url: str
    
    # Basic listing data (from scraping)
    title: str
    asking_price: int
    price_qualifier: str  # guide, offers_over, etc
    
    # Location
    address_line1: str
    address_line2: str
    city: str
    postcode: str
    latitude: float
    longitude: float
    
    # Unit information (extracted/estimated)
    estimated_units: int
    unit_breakdown: JSON  # [{beds: 2, sqft: 500}, ...]
    
    # Title/Tenure (critical for title split)
    tenure: str  # freehold, leasehold, unknown
    tenure_source: str  # listing, epc, land_registry
    tenure_confidence: float
    title_number: str  # if found
    is_single_title: bool  # key indicator
    
    # Condition indicators
    avg_epc_rating: str
    construction_age: str
    refurb_indicators: JSON  # extracted keywords
    
    # Scoring (calculated)
    title_split_score: int  # 0-100
    opportunity_score: int  # 0-100
    
    # Financial projections
    price_per_unit: int
    estimated_individual_values: JSON
    estimated_gross_uplift: int
    estimated_net_uplift: int
    estimated_split_costs: int
    
    # Status
    status: str  # new, analysing, opportunity, rejected, contacted
    rejection_reasons: JSON
    
    # Timestamps
    listed_date: datetime
    first_seen: datetime
    last_analysed: datetime

# Per-unit EPC data
class UnitEPC:
    property_id: UUID
    unit_address: str
    current_rating: str
    potential_rating: str
    floor_area: float
    property_type: str
    construction_age_band: str
    
# Comparable sales
class Comparable:
    property_id: UUID
    address: str
    price: int
    sale_date: date
    beds: int
    property_type: str  # flat, house
    distance_meters: int
    source: str  # land_registry, rightmove_sold

# Analysis results
class Analysis:
    property_id: UUID
    analysis_type: str  # initial, detailed, manual
    
    # Section 1: Title Structure (from framework)
    title_structure_score: int
    title_structure_notes: JSON
    
    # Section 2: Strategic rationale
    exit_strategy_score: int
    financing_benefit_score: int
    
    # Section 5: Cost-benefit
    estimated_costs: JSON
    estimated_benefits: JSON
    net_benefit_per_unit: int
    
    # Section 6: Risk assessment
    risk_score: int
    risk_factors: JSON
    
    # Recommendation
    recommendation: str  # proceed, review, decline
    recommendation_rationale: str
    
    created_at: datetime
```

---


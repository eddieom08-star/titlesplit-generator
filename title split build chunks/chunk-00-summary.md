# Title Split Opportunity Finder - Implementation Guide

## Project Overview

You are building an automated **Title Split Opportunity Finder** - a property investment tool that identifies freehold blocks of flats suitable for title splitting, calculates the post-split GDV (Gross Development Value), and generates lender-grade reports.

**Target User:** UK property investors looking to acquire freehold blocks, split the titles into individual leasehold units, and sell or refinance at a profit.

**Core Value Proposition:** Automate 70% of the due diligence process, provide defensible GDV calculations using real market data, and generate professional reports for lender submissions.

---

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL
- **Data Sources:** PropertyData.co.uk API, Land Registry (free), EPC Open Data (free)
- **AI:** Claude Sonnet 4 for listing analysis and risk assessment
- **Task Queue:** Celery + Redis for background scraping/enrichment
- **Frontend:** React (Phase 4) or start with Slack notifications

---

## Chunk Summary (21 Chunks)

The implementation is broken into 21 self-contained chunks. Each chunk builds on previous ones. Implement them in order.

### Foundation (Chunks 1-4)

| Chunk | Title | Description | Key Outputs |
|-------|-------|-------------|-------------|
| **1** | Project Setup & Core Data Models | SQLAlchemy models, database schema, project structure | `Property`, `UnitEPC`, `Comparable`, `Analysis` models |
| **2** | Rightmove Scraper | Hidden REST API scraper, text extraction for unit count/tenure | `RightmoveScraper` class, keyword patterns |
| **3** | EPC API Integration | UK EPC Open Data API for unit validation and floor areas | `EPCClient`, unit count cross-reference |
| **4** | Land Registry Integration | Price Paid Data SPARQL queries, UKHPI for time adjustments | `LandRegistryClient`, comparable retrieval |

### Analysis Engine (Chunks 5-8)

| Chunk | Title | Description | Key Outputs |
|-------|-------|-------------|-------------|
| **5** | Planning Data Reality Check | Planning portal URL generation (no unified API exists) | Council URL mapping, manual verification flags |
| **6** | AI Analysis Engine | Claude-powered listing analysis, structured JSON output | `AnalysisEngine`, risk flag extraction |
| **7** | Cost-Benefit Calculator | Framework-based cost model, Land Registry fee bands | `CostCalculator`, go/no-go thresholds |
| **8** | Individual Unit Valuation | Comparable-based methodology with condition adjustments | `UnitValuator`, confidence scoring |

### API & Workflow (Chunks 9-12)

| Chunk | Title | Description | Key Outputs |
|-------|-------|-------------|-------------|
| **9** | API Endpoints & Response Models | FastAPI routes, Pydantic models for opportunities | `/opportunities`, `/opportunities/{id}/report` |
| **10** | Background Tasks & Scheduling | Celery tasks, daily scrape, enrichment pipeline | `scrape_all_sources`, `enrich_property` tasks |
| **11** | Data Source Summary Matrix | Documentation of all 30+ data points and their sources | Reference table, automation boundaries |
| **12** | Implementation Phases | 6-phase rollout plan with timelines | Phase definitions, MVP scope |

### Manual Input System (Chunks 13-17)

| Chunk | Title | Description | Key Outputs |
|-------|-------|-------------|-------------|
| **13** | Initial Screening & Automated Recommendation | Recommendation at every stage, even with scraped-only data | `RecommendationEngine`, confidence levels |
| **14** | Manual Input Schema & Validation | Pydantic models for title, planning, physical verification | `ManualInputs`, `TitleVerification`, `HMOLicensing` |
| **15** | Impact Assessment Engine | Rules for how each manual input affects the deal | `Impact` model, blocker detection, scoring adjustments |
| **16** | Recommendation Update Engine | Recalculate recommendation after each manual input | `RecommendationEngine.generate_updated_recommendation()` |
| **17** | Manual Input API Endpoints | REST API for adding/updating manual verification data | `/properties/{id}/manual/*` routes |

### GDV & Lender Reports (Chunks 18-21)

| Chunk | Title | Description | Key Outputs |
|-------|-------|-------------|-------------|
| **18** | Data Source Integration | PropertyData API client, Land Registry SPARQL, EPC client | `PropertyDataClient`, `LandRegistryClient` |
| **19** | Lender-Grade GDV Calculator | Multi-source validation, comparable analysis, AVM cross-check | `GDVCalculator`, `BlockGDVReport` |
| **20** | Lender Report Generation | Professional report format for bridge/development lenders | `LenderGDVReport.generate_report()` |
| **21** | API Integration Summary | Cost analysis, environment variables, sample API calls | Quick reference documentation |

---

## Key Data Models

### Property (Core Entity)
```python
class Property:
    id: UUID
    source: str  # rightmove, zoopla, auction
    source_id: str
    url: str
    address: str
    postcode: str
    price: int
    
    # Extracted data
    estimated_units: int
    tenure: str  # freehold, leasehold, unknown
    tenure_confidence: float
    
    # Enrichment
    epc_validated_units: int
    avg_epc_rating: str
    total_sqft: float
    
    # Analysis
    opportunity_score: int  # 0-100
    estimated_gross_uplift: int
    estimated_net_uplift: int
    
    # Status
    status: str  # new, enriched, analysed, archived
    last_enriched: datetime
```

### ManualInputs (Verification Layer)
```python
class ManualInputs:
    property_id: str
    
    title: TitleInputs  # verification, charges, covenants, easements
    planning: PlanningInputs  # status, HMO licensing
    physical: PhysicalVerification  # inspection results
    financial: FinancialVerification  # valuations, rent roll
```

### BlockGDVReport (Lender Output)
```python
class BlockGDVReport:
    property_address: str
    asking_price: int
    total_units: int
    
    unit_valuations: List[UnitValuation]
    
    total_gdv: int
    gdv_range_low: int
    gdv_range_high: int
    gdv_confidence: ValuationConfidence
    
    gross_uplift: int
    gross_uplift_percent: float
    
    comparables_summary: dict
    data_sources: List[str]
    confidence_statement: str
```

---

## Impact Rules Summary

When manual inputs are added, they affect the deal score:

| Input | Good Value | Impact | Bad Value | Impact |
|-------|-----------|--------|-----------|--------|
| Tenure | Freehold | +30 | Leasehold | **BLOCKER** |
| Single title | Yes | +20 | Already split | **BLOCKER** |
| Title class | Absolute | +5 | Possessory | -30 |
| Lender consent | Likely | -10 | Refused | **BLOCKER** |
| Use class | C3 | +15 | Sui generis | -25 |
| Conversion consent | Yes | +20 | No | -40 |
| HMO licence | Held | 0 | Required but missing | **BLOCKER** |
| Self-contained | All units | +25 | Not self-contained | -40 |

---

## API Data Sources

| Source | Cost | Endpoints Used |
|--------|------|----------------|
| **PropertyData.co.uk** | £28/mo | `/valuation-sale`, `/sold-prices`, `/sold-prices-per-sqf`, `/yields` |
| **Land Registry PPD** | Free | SPARQL queries for transaction data |
| **Land Registry UKHPI** | Free | SPARQL/CSV for price indices |
| **EPC Open Data** | Free | `/domestic/search` for floor areas, ratings |

---

## Go/No-Go Thresholds (From Framework)

| Decision | Criteria |
|----------|----------|
| ✅ **Proceed** | Net benefit >£2,000 per unit AND no blockers |
| ⚠️ **Review** | Marginal benefit but strategic value |
| ❌ **Decline** | Transaction costs >3% of value OR any blocker present |

---

## Directory Structure

```
title-split-finder/
├── src/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── config.py               # Settings
│   ├── database.py             # DB connection
│   │
│   ├── models/
│   │   ├── property.py         # SQLAlchemy models
│   │   ├── manual_inputs.py    # Pydantic input models
│   │   └── reports.py          # Report models
│   │
│   ├── scrapers/
│   │   ├── rightmove.py
│   │   ├── zoopla.py
│   │   └── auctions.py
│   │
│   ├── data_sources/
│   │   ├── property_data.py    # PropertyData API client
│   │   ├── land_registry.py    # Land Registry SPARQL
│   │   ├── epc.py              # EPC API client
│   │   └── planning.py         # Planning portal URLs
│   │
│   ├── analysis/
│   │   ├── screening.py        # Initial pass/fail
│   │   ├── ai_analysis.py      # Claude integration
│   │   ├── cost_calculator.py  # Cost model
│   │   ├── gdv_calculator.py   # GDV engine
│   │   ├── impact_rules.py     # Manual input impacts
│   │   └── recommendation.py   # Recommendation engine
│   │
│   ├── api/
│   │   ├── opportunities.py    # Main endpoints
│   │   ├── manual_inputs.py    # Verification endpoints
│   │   └── reports.py          # Report generation
│   │
│   ├── tasks/
│   │   ├── scraping.py         # Celery scrape tasks
│   │   ├── enrichment.py       # Enrichment pipeline
│   │   └── notifications.py    # Slack/email alerts
│   │
│   └── reports/
│       ├── gdv_report.py       # Lender report generator
│       └── templates/          # Report templates
│
├── tests/
├── alembic/                    # DB migrations
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Implementation Order

1. **Start with Chunk 1** - Get the data models and database set up
2. **Chunks 2-4** - Build the data ingestion pipeline
3. **Chunks 5-8** - Implement analysis logic
4. **Chunks 9-10** - Wire up API and background tasks
5. **Chunks 13-17** - Add manual input system
6. **Chunks 18-20** - Implement GDV calculator and reports

**MVP Milestone (Chunks 1-10):** Working scraper → enrichment → scoring → API
**Full System (Chunks 1-21):** Complete with manual inputs and lender reports

---

## Ready to Start

You will receive 21 chunks sequentially. Each chunk contains:
- Detailed requirements
- Code examples (Python/FastAPI)
- Data models
- API contracts
- Integration notes

Implement each chunk fully before moving to the next. Ask questions if anything is unclear.

**First chunk incoming: Project Setup & Core Data Models**

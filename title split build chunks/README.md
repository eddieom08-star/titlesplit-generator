# Title Split Opportunity Finder - Implementation Chunks

## How to Use

1. **First:** Feed `chunk-00-summary.md` to Claude Code to set context
2. **Then:** Feed chunks 1-21 in order, one at a time
3. **After each chunk:** Let Claude Code implement before sending the next

---

## Chunk Index

| File | Title | Lines | Key Deliverables |
|------|-------|-------|------------------|
| `chunk-00-summary.md` | **Implementation Guide** | 200 | Architecture overview, data models, tech stack |
| `chunk-01-project-setup.md` | Project Setup & Core Data Models | 126 | SQLAlchemy models, database schema |
| `chunk-02-rightmove-scraper.md` | Rightmove Scraper | 132 | REST API scraper, text extraction |
| `chunk-03-epc-integration.md` | EPC API Integration | 93 | EPC client, unit validation |
| `chunk-04-land-registry.md` | Land Registry Integration | 70 | SPARQL queries, PPD data |
| `chunk-05-planning-data.md` | Planning Data | 46 | Council URL mapping |
| `chunk-06-ai-analysis.md` | AI Analysis Engine | 213 | Claude integration, risk extraction |
| `chunk-07-cost-calculator.md` | Cost-Benefit Calculator | 162 | Cost model, go/no-go thresholds |
| `chunk-08-unit-valuation.md` | Unit Valuation | 113 | Comparable-based methodology |
| `chunk-09-api-endpoints.md` | API Endpoints | 205 | FastAPI routes, response models |
| `chunk-10-background-tasks.md` | Background Tasks | 106 | Celery tasks, scheduling |
| `chunk-11-data-matrix.md` | Data Source Matrix | 36 | Source documentation |
| `chunk-12-implementation-phases.md` | Implementation Phases | 99 | 6-phase rollout plan |
| `chunk-13-initial-recommendation.md` | Initial Recommendation | 182 | Recommendation engine (automated) |
| `chunk-14-manual-input-schema.md` | Manual Input Schema | 389 | Pydantic models for verification |
| `chunk-15-impact-assessment.md` | Impact Assessment Engine | 907 | Impact rules, blocker detection |
| `chunk-16-recommendation-engine.md` | Recommendation Update | 347 | Recalculation after manual inputs |
| `chunk-17-manual-input-api.md` | Manual Input API | 345 | REST endpoints for verification |
| `chunk-18-data-sources.md` | Data Source Integration | 524 | PropertyData, Land Registry clients |
| `chunk-19-gdv-calculator.md` | GDV Calculator | 530 | Multi-source GDV engine |
| `chunk-20-lender-reports.md` | Lender Reports | 303 | Professional report generation |
| `chunk-21-api-summary.md` | API Summary | 76 | Cost analysis, env variables |

---

## Suggested Implementation Order

### Phase 1: Foundation (MVP)
```
chunk-01 → chunk-02 → chunk-03 → chunk-04 → chunk-05
```
Data models and ingestion pipeline

### Phase 2: Analysis
```
chunk-06 → chunk-07 → chunk-08
```
AI analysis and valuation

### Phase 3: API & Automation
```
chunk-09 → chunk-10 → chunk-11 → chunk-12
```
REST API and background tasks

### Phase 4: Manual Verification
```
chunk-13 → chunk-14 → chunk-15 → chunk-16 → chunk-17
```
Manual input system with impact assessment

### Phase 5: GDV & Reports
```
chunk-18 → chunk-19 → chunk-20 → chunk-21
```
Lender-grade valuations and reports

---

## Quick Start Prompt

Copy this to start Claude Code:

```
I'm building a Title Split Opportunity Finder. Please read the implementation 
guide (chunk-00-summary.md) first. You will receive 21 implementation chunks 
in sequence. Each chunk builds on the previous ones.

After reading the summary, confirm you understand the architecture and are 
ready for Chunk 1.
```

---

## File Sizes

- **Small chunks** (< 100 lines): 5, 11 - quick to implement
- **Medium chunks** (100-200 lines): 1, 2, 3, 4, 6, 7, 8, 10, 12, 13 - core features
- **Large chunks** (200-400 lines): 9, 14, 16, 17, 20 - detailed implementations
- **XL chunks** (400+ lines): 15, 18, 19 - comprehensive modules

Total: ~5,000 lines of specification across 21 chunks

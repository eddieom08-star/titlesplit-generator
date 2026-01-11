## CHUNK 12: Implementation Phases

### Phase 1: MVP (2 weeks)

**Goal:** Working pipeline that identifies opportunities from Rightmove.

**Deliverables:**
- [ ] Rightmove scraper (search + detail fetch)
- [ ] PostgreSQL schema and models
- [ ] Text extraction for units, tenure, refurb
- [ ] Initial screening filter
- [ ] Basic scoring (no AI)
- [ ] Simple API to list properties
- [ ] Slack notification for new properties

**Data Sources:** Rightmove only, text extraction only.

### Phase 2: Enrichment (2 weeks)

**Goal:** Add EPC data and comparables for better analysis.

**Deliverables:**
- [ ] EPC API integration
- [ ] Unit count validation from EPCs
- [ ] Land Registry Price Paid integration
- [ ] Comparable-based valuation
- [ ] Cost calculator
- [ ] Benefit calculator
- [ ] Enhanced scoring algorithm

**Data Sources:** + EPC API, + Land Registry PPD.

### Phase 3: AI Analysis (1 week)

**Goal:** Claude-powered deep analysis.

**Deliverables:**
- [ ] AI analysis prompt engineering
- [ ] Structured output parsing
- [ ] Confidence scoring
- [ ] Risk identification
- [ ] Recommendation generation

**Data Sources:** + Claude API.

### Phase 4: Frontend (2 weeks)

**Goal:** Dashboard to browse and manage opportunities.

**Deliverables:**
- [ ] Deal feed with filters
- [ ] Property detail page
- [ ] Score breakdown visualisation
- [ ] Cost/benefit summary
- [ ] Due diligence checklist
- [ ] Status management (pipeline)
- [ ] Export to PDF/Word

### Phase 5: Multi-Source (1 week)

**Goal:** Add Zoopla and auction sources.

**Deliverables:**
- [ ] Zoopla scraper
- [ ] Auction house scrapers (Allsop, SDL)
- [ ] Source deduplication
- [ ] Source comparison

### Phase 6: Advanced Features (ongoing)

**Potential:**
- [ ] Email alert parsing
- [ ] Price drop detection
- [ ] Market trend analytics
- [ ] Automated report generation
- [ ] Mobile app

---

## Manual Verification Checklist

**Items that MUST be manually verified before proceeding:**

| Item | How to Verify | Cost | Time |
|------|---------------|------|------|
| Title is single freehold | Land Registry title search | £3 | 5 min |
| No charges preventing sale | Land Registry title search | (included) | 5 min |
| No restrictive covenants | Land Registry title search | (included) | 10 min |
| Units are self-contained | Physical viewing | Free | 1 hour |
| Planning compliant | Council planning portal | Free | 30 min |
| No HMO licensing issues | Council HMO register | Free | 15 min |
| Structural condition | Survey | £300-500 | 2-3 hours |
| Lender will consent | Lender enquiry | Free | 1-2 weeks |

---

*Specification Version 1.0 | Title Split Opportunity Finder*
# Title Split Opportunity Finder


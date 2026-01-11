## CHUNK 10: Background Tasks & Scheduling

### 10.1 Scheduled Tasks

```python
# src/tasks/scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# Daily scrape at 7am
@scheduler.scheduled_job('cron', hour=7)
async def daily_scrape():
    """
    Run daily property scrape across all sources and locations.
    """
    from .scrape_all import scrape_all_sources
    await scrape_all_sources()

# Enrichment every 2 hours
@scheduler.scheduled_job('interval', hours=2)
async def enrich_pending():
    """
    Enrich properties that haven't been analysed yet.
    """
    from .enrich_properties import enrich_pending_properties
    await enrich_pending_properties(batch_size=20)

# Daily digest at 6pm
@scheduler.scheduled_job('cron', hour=18)
async def send_daily_digest():
    """
    Send daily digest of hot opportunities.
    """
    from .notifications import send_digest
    await send_digest()

# Weekly market stats on Monday 9am
@scheduler.scheduled_job('cron', day_of_week='mon', hour=9)
async def weekly_stats():
    """
    Generate weekly market statistics.
    """
    from .analytics import generate_weekly_stats
    await generate_weekly_stats()
```

### 10.2 Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        DAILY PIPELINE                            │
└─────────────────────────────────────────────────────────────────┘

07:00 ─────> SCRAPE
             │
             ├── Rightmove (all target locations)
             ├── Zoopla (all target locations)
             └── Auctions (weekly catalogues)
                     │
                     ▼
             INGEST & DEDUPE
             │
             ├── Normalise data to schema
             ├── Check for duplicates (source_id)
             └── Update prices if changed
                     │
                     ▼
             INITIAL SCREEN
             │
             ├── Hard criteria filter
             ├── Extract unit count, tenure
             └── Flag red flags
                     │
                     ▼
             Status: "pending_enrichment"

09:00 ─────> ENRICH (batch 1)
11:00 ─────> ENRICH (batch 2)
13:00 ─────> ENRICH (batch 3)
15:00 ─────> ENRICH (batch 4)
             │
             ├── EPC API lookup
             ├── Land Registry comparables
             └── AI deep analysis
                     │
                     ▼
             SCORE & RANK
             │
             ├── Calculate opportunity score
             ├── Estimate costs/benefits
             └── Generate recommendation
                     │
                     ▼
             Status: "analysed"

18:00 ─────> NOTIFY
             │
             ├── Hot deals (score 85+) -> Slack immediately
             ├── Good deals (70-84) -> Daily digest
             └── Watchlist (60-69) -> Weekly summary
```

---


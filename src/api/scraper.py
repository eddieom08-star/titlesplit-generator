"""API endpoints for triggering and monitoring scraper tasks."""
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
import structlog

from src.tasks.scraping import scrape_all_sources, scrape_rightmove
from src.tasks.enrichment import enrich_pending_properties
from src.database import AsyncSessionLocal
from src.models.property import Property

logger = structlog.get_logger()
router = APIRouter(prefix="/scraper", tags=["scraper"])


@router.post("/trigger")
async def trigger_scrape(background_tasks: BackgroundTasks):
    """
    Trigger a full scrape of all sources.

    Runs in background and returns immediately.
    """
    background_tasks.add_task(run_scrape)
    return {"status": "started", "message": "Scrape job triggered in background"}


@router.post("/trigger/rightmove")
async def trigger_rightmove_scrape(
    location: str = "london",
    background_tasks: BackgroundTasks = None,
):
    """
    Trigger a Rightmove scrape for a specific location.
    """
    background_tasks.add_task(run_rightmove_scrape, location)
    return {"status": "started", "location": location}


@router.post("/enrich")
async def trigger_enrichment(
    batch_size: int = 10,
    background_tasks: BackgroundTasks = None,
):
    """
    Trigger enrichment of pending properties.

    Fetches EPC data, comparables, and runs AI analysis.
    """
    background_tasks.add_task(run_enrichment, batch_size)
    return {"status": "started", "batch_size": batch_size}


async def run_scrape():
    """Run full scrape."""
    try:
        logger.info("Starting manual scrape trigger")
        results = await scrape_all_sources()
        logger.info("Manual scrape completed", **results)
    except Exception as e:
        logger.error("Manual scrape failed", error=str(e))


async def run_rightmove_scrape(location: str):
    """Run Rightmove scrape for location."""
    try:
        logger.info("Starting Rightmove scrape", location=location)
        results = await scrape_rightmove(location)
        logger.info("Rightmove scrape completed", **results)
    except Exception as e:
        logger.error("Rightmove scrape failed", error=str(e))


async def run_enrichment(batch_size: int):
    """Run enrichment."""
    try:
        logger.info("Starting enrichment", batch_size=batch_size)
        results = await enrich_pending_properties(batch_size=batch_size)
        logger.info("Enrichment completed", **results)
    except Exception as e:
        logger.error("Enrichment failed", error=str(e))


@router.post("/seed")
async def seed_demo_data():
    """
    Seed the database with demo properties for testing.
    """
    demo_properties = [
        {
            "title": "Block of 4 Flats - Freehold Investment",
            "asking_price": 280000,
            "address_line1": "42 Victoria Road",
            "city": "Liverpool",
            "postcode": "L15 8HU",
            "estimated_units": 4,
            "tenure": "freehold",
            "tenure_confidence": 0.95,
            "opportunity_score": 78,
            "estimated_gross_uplift": 95000,
            "estimated_net_uplift": 72000,
        },
        {
            "title": "Freehold Block - 3 Self-Contained Flats",
            "asking_price": 195000,
            "address_line1": "18 Boundary Lane",
            "city": "Manchester",
            "postcode": "M14 7NQ",
            "estimated_units": 3,
            "tenure": "freehold",
            "tenure_confidence": 0.90,
            "opportunity_score": 82,
            "estimated_gross_uplift": 75000,
            "estimated_net_uplift": 58000,
        },
        {
            "title": "Investment Opportunity - 5 Unit Freehold",
            "asking_price": 375000,
            "address_line1": "7 Park Street",
            "city": "Leeds",
            "postcode": "LS9 8AQ",
            "estimated_units": 5,
            "tenure": "freehold",
            "tenure_confidence": 0.85,
            "opportunity_score": 71,
            "estimated_gross_uplift": 110000,
            "estimated_net_uplift": 82000,
        },
        {
            "title": "Freehold Block of 6 Flats - Refurb Required",
            "asking_price": 320000,
            "address_line1": "91 High Street",
            "city": "Sheffield",
            "postcode": "S2 4QR",
            "estimated_units": 6,
            "tenure": "freehold",
            "tenure_confidence": 0.92,
            "opportunity_score": 68,
            "estimated_gross_uplift": 140000,
            "estimated_net_uplift": 95000,
            "refurb_indicators": [{"type": "needs_work", "confidence": 0.8}],
        },
        {
            "title": "3 Bed Maisonette Block - Freehold",
            "asking_price": 165000,
            "address_line1": "25 Church Road",
            "city": "Bradford",
            "postcode": "BD5 0JB",
            "estimated_units": 2,
            "tenure": "freehold",
            "tenure_confidence": 0.88,
            "opportunity_score": 65,
            "estimated_gross_uplift": 45000,
            "estimated_net_uplift": 32000,
        },
    ]

    created = 0
    async with AsyncSessionLocal() as session:
        for prop_data in demo_properties:
            prop = Property(
                id=uuid4(),
                source="demo",
                source_id=f"demo-{uuid4().hex[:8]}",
                source_url=f"https://example.com/property/{uuid4().hex[:8]}",
                title=prop_data["title"],
                asking_price=prop_data["asking_price"],
                address_line1=prop_data["address_line1"],
                city=prop_data["city"],
                postcode=prop_data["postcode"],
                estimated_units=prop_data["estimated_units"],
                tenure=prop_data["tenure"],
                tenure_confidence=prop_data.get("tenure_confidence"),
                opportunity_score=prop_data["opportunity_score"],
                estimated_gross_uplift=prop_data.get("estimated_gross_uplift"),
                estimated_net_uplift=prop_data.get("estimated_net_uplift"),
                refurb_indicators=prop_data.get("refurb_indicators"),
                status="pending_enrichment",
                first_seen=datetime.utcnow(),
                price_per_unit=prop_data["asking_price"] // prop_data["estimated_units"],
            )
            session.add(prop)
            created += 1

        await session.commit()

    logger.info("Demo data seeded", count=created)
    return {"status": "seeded", "count": created}

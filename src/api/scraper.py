"""API endpoints for triggering and monitoring scraper tasks."""
from fastapi import APIRouter, BackgroundTasks, HTTPException
import structlog

from src.tasks.scraping import scrape_all_sources, scrape_rightmove
from src.tasks.enrichment import enrich_pending_properties

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

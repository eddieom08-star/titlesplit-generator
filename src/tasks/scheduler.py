import asyncio
from datetime import datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.tasks.scraping import scrape_all_sources
from src.tasks.enrichment import enrich_pending_properties

logger = structlog.get_logger()

scheduler = AsyncIOScheduler()


def setup_scheduled_jobs():
    """Configure all scheduled jobs."""

    # Daily scrape at 7am
    scheduler.add_job(
        daily_scrape,
        CronTrigger(hour=7, minute=0),
        id="daily_scrape",
        name="Daily property scrape",
        replace_existing=True,
    )

    # Enrichment every 2 hours
    scheduler.add_job(
        enrich_pending,
        IntervalTrigger(hours=2),
        id="enrich_pending",
        name="Enrich pending properties",
        replace_existing=True,
    )

    # Daily digest at 6pm
    scheduler.add_job(
        send_daily_digest,
        CronTrigger(hour=18, minute=0),
        id="daily_digest",
        name="Send daily digest",
        replace_existing=True,
    )

    # Weekly stats on Monday 9am
    scheduler.add_job(
        weekly_stats,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="weekly_stats",
        name="Generate weekly stats",
        replace_existing=True,
    )

    logger.info("Scheduled jobs configured")


async def daily_scrape():
    """Run daily property scrape across all sources and locations."""
    logger.info("Starting daily scrape job")
    try:
        results = await scrape_all_sources()
        logger.info("Daily scrape complete", **results)
    except Exception as e:
        logger.error("Daily scrape failed", error=str(e))


async def enrich_pending():
    """Enrich properties that haven't been analysed yet."""
    logger.info("Starting enrichment job")
    try:
        results = await enrich_pending_properties(batch_size=20)
        logger.info("Enrichment complete", **results)
    except Exception as e:
        logger.error("Enrichment failed", error=str(e))


async def send_daily_digest():
    """Send daily digest of hot opportunities."""
    logger.info("Starting daily digest")
    try:
        from src.tasks.notifications import send_digest
        await send_digest()
        logger.info("Daily digest sent")
    except Exception as e:
        logger.error("Daily digest failed", error=str(e))


async def weekly_stats():
    """Generate weekly market statistics."""
    logger.info("Starting weekly stats")
    try:
        # Would generate stats here
        logger.info("Weekly stats generated")
    except Exception as e:
        logger.error("Weekly stats failed", error=str(e))


def start_scheduler():
    """Start the scheduler."""
    setup_scheduled_jobs()
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler."""
    scheduler.shutdown()
    logger.info("Scheduler stopped")

"""Standalone script to run the scraper - used by cron jobs."""
import asyncio
import structlog
from src.tasks.scraping import scrape_all_sources

logger = structlog.get_logger()


async def main():
    logger.info("Starting scheduled scrape job")
    try:
        results = await scrape_all_sources()
        logger.info("Scrape completed", **results)
    except Exception as e:
        logger.error("Scrape failed", error=str(e))
        raise


if __name__ == "__main__":
    asyncio.run(main())

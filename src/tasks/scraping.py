import asyncio
from datetime import datetime
from typing import Optional
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.property import Property
from src.scrapers.rightmove import RightmoveScraper, ScrapedProperty, SEARCH_CONFIGS, LOCATIONS
from src.scrapers.onthemarket import OnTheMarketScraper, OTM_SEARCH_CONFIGS, OTM_LOCATIONS
from src.scrapers.loopnet import LoopNetScraper, LOOPNET_SEARCH_CONFIGS, LOOPNET_LOCATIONS
from src.analysis.screening import initial_screen

logger = structlog.get_logger()


async def scrape_all_sources(
    locations: Optional[dict] = None,
    configs: Optional[list] = None,
) -> dict:
    """
    Run scrape across all sources and locations.

    Returns summary of scrape results.
    """
    results = {
        "started_at": datetime.utcnow().isoformat(),
        "sources": {},
        "total_scraped": 0,
        "total_new": 0,
        "total_updated": 0,
    }

    # Scrape Rightmove
    try:
        logger.info("Starting Rightmove scrape")
        rightmove_results = await scrape_rightmove(locations or LOCATIONS, configs or SEARCH_CONFIGS)
        results["sources"]["rightmove"] = rightmove_results
        results["total_scraped"] += rightmove_results["scraped"]
        results["total_new"] += rightmove_results["new"]
        results["total_updated"] += rightmove_results["updated"]
    except Exception as e:
        logger.error("Rightmove scrape failed", error=str(e))
        results["sources"]["rightmove"] = {"error": str(e), "scraped": 0, "new": 0, "updated": 0}

    # Scrape OnTheMarket
    try:
        logger.info("Starting OnTheMarket scrape")
        otm_results = await scrape_onthemarket()
        results["sources"]["onthemarket"] = otm_results
        results["total_scraped"] += otm_results["scraped"]
        results["total_new"] += otm_results["new"]
        results["total_updated"] += otm_results["updated"]
    except Exception as e:
        logger.error("OnTheMarket scrape failed", error=str(e))
        results["sources"]["onthemarket"] = {"error": str(e), "scraped": 0, "new": 0, "updated": 0}

    # Scrape LoopNet
    try:
        logger.info("Starting LoopNet scrape")
        loopnet_results = await scrape_loopnet()
        results["sources"]["loopnet"] = loopnet_results
        results["total_scraped"] += loopnet_results["scraped"]
        results["total_new"] += loopnet_results["new"]
        results["total_updated"] += loopnet_results["updated"]
    except Exception as e:
        logger.error("LoopNet scrape failed", error=str(e))
        results["sources"]["loopnet"] = {"error": str(e), "scraped": 0, "new": 0, "updated": 0}

    results["completed_at"] = datetime.utcnow().isoformat()
    logger.info("Scrape complete", **results)

    return results


async def scrape_rightmove(
    locations: dict,
    configs: list,
) -> dict:
    """Scrape Rightmove for all locations and configs."""
    scraper = RightmoveScraper()
    all_properties = []

    for config in configs:
        try:
            properties = await scraper.search_all_locations(config, locations)
            all_properties.extend(properties)
            logger.info(
                "Config scrape complete",
                config=config.get("keywords"),
                count=len(properties),
            )
        except Exception as e:
            logger.error("Config scrape failed", config=config, error=str(e))

    # Deduplicate by source_id
    seen_ids = set()
    unique_properties = []
    for prop in all_properties:
        if prop.source_id not in seen_ids:
            seen_ids.add(prop.source_id)
            unique_properties.append(prop)

    # Ingest into database
    new_count = 0
    updated_count = 0

    async with AsyncSessionLocal() as session:
        for scraped in unique_properties:
            is_new, is_updated = await ingest_property(session, scraped, source="rightmove")
            if is_new:
                new_count += 1
            elif is_updated:
                updated_count += 1

        await session.commit()

    return {
        "scraped": len(unique_properties),
        "new": new_count,
        "updated": updated_count,
    }


async def scrape_onthemarket() -> dict:
    """Scrape OnTheMarket for all locations and configs."""
    scraper = OnTheMarketScraper()
    all_properties = []

    for config in OTM_SEARCH_CONFIGS:
        try:
            properties = await scraper.search_all_locations(config, OTM_LOCATIONS)
            all_properties.extend(properties)
            logger.info(
                "OTM config scrape complete",
                config=config.get("keywords"),
                count=len(properties),
            )
        except Exception as e:
            logger.error("OTM config scrape failed", config=config, error=str(e))

    # Deduplicate by source_id
    seen_ids = set()
    unique_properties = []
    for prop in all_properties:
        if prop.source_id not in seen_ids:
            seen_ids.add(prop.source_id)
            unique_properties.append(prop)

    # Ingest into database
    new_count = 0
    updated_count = 0

    async with AsyncSessionLocal() as session:
        for scraped in unique_properties:
            is_new, is_updated = await ingest_property(session, scraped, source="onthemarket")
            if is_new:
                new_count += 1
            elif is_updated:
                updated_count += 1

        await session.commit()

    return {
        "scraped": len(unique_properties),
        "new": new_count,
        "updated": updated_count,
    }


async def scrape_loopnet() -> dict:
    """Scrape LoopNet for all locations and configs."""
    scraper = LoopNetScraper()
    all_properties = []

    for config in LOOPNET_SEARCH_CONFIGS:
        try:
            properties = await scraper.search_all_locations(config, LOOPNET_LOCATIONS)
            all_properties.extend(properties)
            logger.info(
                "LoopNet config scrape complete",
                config=config.get("property_type"),
                count=len(properties),
            )
        except Exception as e:
            logger.error("LoopNet config scrape failed", config=config, error=str(e))

    # Deduplicate by source_id
    seen_ids = set()
    unique_properties = []
    for prop in all_properties:
        if prop.source_id not in seen_ids:
            seen_ids.add(prop.source_id)
            unique_properties.append(prop)

    # Ingest into database
    new_count = 0
    updated_count = 0

    async with AsyncSessionLocal() as session:
        for scraped in unique_properties:
            is_new, is_updated = await ingest_property(session, scraped, source="loopnet")
            if is_new:
                new_count += 1
            elif is_updated:
                updated_count += 1

        await session.commit()

    return {
        "scraped": len(unique_properties),
        "new": new_count,
        "updated": updated_count,
    }


async def ingest_property(
    session: AsyncSession,
    scraped: ScrapedProperty,
    source: str = "rightmove",
) -> tuple[bool, bool]:
    """
    Ingest a scraped property into the database.

    Returns: (is_new, is_updated)
    """
    # Check if exists
    result = await session.execute(
        select(Property).where(
            Property.source == source,
            Property.source_id == scraped.source_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update if price changed
        if existing.asking_price != scraped.asking_price:
            existing.asking_price = scraped.asking_price
            existing.updated_at = datetime.utcnow()
            return False, True
        return False, False

    # Create new property
    property = Property(
        id=uuid4(),
        source=source,
        source_id=scraped.source_id,
        source_url=scraped.source_url,
        title=scraped.title,
        asking_price=scraped.asking_price,
        price_qualifier=scraped.price_qualifier,
        address_line1=scraped.address_line1,
        address_line2=scraped.address_line2,
        city=scraped.city,
        postcode=scraped.postcode,
        latitude=scraped.latitude,
        longitude=scraped.longitude,
        estimated_units=scraped.estimated_units,
        tenure=scraped.tenure,
        tenure_confidence=scraped.tenure_confidence,
        refurb_indicators=scraped.refurb_indicators,
        status="new",
        first_seen=datetime.utcnow(),
        listed_date=scraped.listed_date,
    )

    # Calculate price per unit
    if property.estimated_units and property.estimated_units > 0:
        property.price_per_unit = property.asking_price // property.estimated_units

    # Run initial screening
    screening = initial_screen(property)
    if not screening.passes:
        property.status = "rejected"
        property.rejection_reasons = {"reasons": screening.rejections}
    else:
        property.status = "pending_enrichment"
        property.opportunity_score = screening.score

    session.add(property)
    return True, False


async def get_pending_properties(
    session: AsyncSession,
    batch_size: int = 20,
) -> list[Property]:
    """Get properties pending enrichment."""
    result = await session.execute(
        select(Property)
        .where(Property.status == "pending_enrichment")
        .order_by(Property.first_seen.desc())
        .limit(batch_size)
    )
    return list(result.scalars().all())

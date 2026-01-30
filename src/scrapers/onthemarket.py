import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import structlog

from src.scrapers.extractors import (
    extract_unit_count,
    extract_tenure,
    extract_refurb_indicators,
    extract_red_flags,
    extract_postcode,
    extract_bedrooms,
    extract_floor_area,
    extract_total_bedrooms,
)
from src.scrapers.rightmove import ScrapedProperty

logger = structlog.get_logger()

# OnTheMarket search URLs for block of flats
OTM_LOCATIONS = {
    "uk-wide": "uk",
    "liverpool": "liverpool",
    "manchester": "manchester",
    "leeds": "leeds",
    "sheffield": "sheffield",
    "bradford": "bradford",
    "newcastle": "newcastle-upon-tyne",
    "hull": "hull",
    "middlesbrough": "middlesbrough",
}

OTM_SEARCH_CONFIGS = [
    {
        "keywords": "block of flats",
        "min_price": 100000,
        "max_price": 800000,
    },
    {
        "keywords": "investment freehold",
        "min_price": 100000,
        "max_price": 800000,
    },
    {
        "keywords": "flats freehold",
        "min_price": 100000,
        "max_price": 800000,
    },
]


class OnTheMarketScraper:
    """Scraper for OnTheMarket property listings using Playwright."""

    BASE_URL = "https://www.onthemarket.com"
    RATE_LIMIT_SECONDS = 3.0

    def __init__(self, headless: bool = True, timeout: float = 30000):
        self.headless = headless
        self.timeout = timeout
        self._last_request_time: Optional[float] = None

    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        if self._last_request_time:
            elapsed = asyncio.get_event_loop().time() - self._last_request_time
            if elapsed < self.RATE_LIMIT_SECONDS:
                await asyncio.sleep(self.RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    def _build_search_url(
        self,
        location: str,
        keywords: str = "",
        min_price: int = 0,
        max_price: int = 0,
        page: int = 1,
    ) -> str:
        """Build search URL for OnTheMarket."""
        base = f"{self.BASE_URL}/for-sale/{location}"
        params = []

        if min_price > 0:
            params.append(f"min-price={min_price}")
        if max_price > 0:
            params.append(f"max-price={max_price}")
        if keywords:
            params.append(f"keywords={keywords.replace(' ', '+')}")
        if page > 1:
            params.append(f"page={page}")

        if params:
            return f"{base}?{'&'.join(params)}"
        return base

    async def search(
        self,
        location: str,
        keywords: str = "",
        min_price: int = 0,
        max_price: int = 0,
        max_pages: int = 3,
    ) -> list[ScrapedProperty]:
        """Search OnTheMarket using Playwright browser automation."""
        properties = []

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = await context.new_page()

            for page_num in range(1, max_pages + 1):
                await self._rate_limit()

                url = self._build_search_url(
                    location=location,
                    keywords=keywords,
                    min_price=min_price,
                    max_price=max_price,
                    page=page_num,
                )

                try:
                    logger.info("Fetching OTM page", url=url, page=page_num)
                    await page.goto(url, timeout=self.timeout)
                    await page.wait_for_load_state("networkidle", timeout=self.timeout)

                    # Wait for listings to load
                    await page.wait_for_selector('[data-test="property-card"]', timeout=10000)

                    # Extract listings
                    listings = await page.query_selector_all('[data-test="property-card"]')
                    if not listings:
                        logger.info("No more listings", page=page_num)
                        break

                    for listing in listings:
                        try:
                            prop = await self._parse_listing(listing, page)
                            if prop:
                                properties.append(prop)
                        except Exception as e:
                            logger.warning("Failed to parse OTM listing", error=str(e))

                except Exception as e:
                    logger.error("OTM page fetch failed", error=str(e), url=url)
                    break

            await browser.close()

        return properties

    async def _parse_listing(self, listing, page) -> Optional[ScrapedProperty]:
        """Parse a single listing element."""
        try:
            # Extract property link and ID
            link_element = await listing.query_selector('a[href*="/details/"]')
            if not link_element:
                return None

            href = await link_element.get_attribute("href")
            if not href:
                return None

            # Extract property ID from URL
            match = re.search(r'/details/(\d+)', href)
            if not match:
                return None
            property_id = match.group(1)

            # Extract price
            price_element = await listing.query_selector('[data-test="price"]')
            price_text = await price_element.inner_text() if price_element else "0"
            asking_price = self._parse_price(price_text)
            if not asking_price:
                return None

            # Extract address
            address_element = await listing.query_selector('[data-test="address"]')
            address_text = await address_element.inner_text() if address_element else ""
            address_parts = address_text.split(", ")
            address_line1 = address_parts[0] if address_parts else address_text
            city = address_parts[-1] if len(address_parts) > 1 else ""
            postcode = extract_postcode(address_text) or ""

            # Extract description/summary
            desc_element = await listing.query_selector('[data-test="description"]')
            description = await desc_element.inner_text() if desc_element else ""

            # Extract title/property type
            title_element = await listing.query_selector('[data-test="property-type"]')
            title = await title_element.inner_text() if title_element else "Property"

            # Extract images
            images = []
            img_elements = await listing.query_selector_all('img')
            for img in img_elements:
                src = await img.get_attribute("src")
                if src and "placeholder" not in src.lower():
                    images.append(src)

            # Extract agent name
            agent_element = await listing.query_selector('[data-test="agent-name"]')
            agent_name = await agent_element.inner_text() if agent_element else None

            # Full text for extraction
            full_text = f"{title} {description} {address_text}"

            # Run text extraction
            unit_result = extract_unit_count(full_text)
            tenure_result = extract_tenure(full_text)
            refurb_indicators = extract_refurb_indicators(full_text)
            red_flags = extract_red_flags(full_text)
            bedroom_breakdown = extract_bedrooms(full_text)
            floor_area_result = extract_floor_area(full_text, None)
            total_beds_result = extract_total_bedrooms(full_text)

            return ScrapedProperty(
                source_id=f"otm_{property_id}",
                source_url=f"{self.BASE_URL}{href}",
                title=title,
                asking_price=asking_price,
                price_qualifier=None,
                address_line1=address_line1,
                address_line2=None,
                city=city,
                postcode=postcode,
                latitude=None,
                longitude=None,
                description=description,
                images=images,
                agent_name=agent_name,
                estimated_units=unit_result.value,
                unit_confidence=unit_result.confidence,
                tenure=tenure_result.value,
                tenure_confidence=tenure_result.confidence,
                refurb_indicators=refurb_indicators,
                red_flags=red_flags,
                bedroom_breakdown=bedroom_breakdown,
                listed_date=None,
                raw_data={"source": "onthemarket", "id": property_id},
                bedrooms=total_beds_result.value,
                bathrooms=None,
                floor_area_sqft=floor_area_result.sqft,
                floor_area_sqm=floor_area_result.sqm,
                floor_area_source=floor_area_result.source,
                property_type=title,
                has_floorplan=False,
            )

        except Exception as e:
            logger.warning("Error parsing OTM listing", error=str(e))
            return None

    def _parse_price(self, price_text: str) -> Optional[int]:
        """Parse price from text like '£250,000' or 'Guide Price £250,000'."""
        match = re.search(r'£([\d,]+)', price_text)
        if match:
            return int(match.group(1).replace(',', ''))
        return None

    async def search_all_locations(
        self,
        config: dict,
        locations: Optional[dict] = None,
    ) -> list[ScrapedProperty]:
        """Search across all configured locations."""
        locations = locations or OTM_LOCATIONS
        all_properties = []

        for location_name, location_slug in locations.items():
            logger.info("Searching OTM location", location=location_name)

            properties = await self.search(
                location=location_slug,
                keywords=config.get("keywords", ""),
                min_price=config.get("min_price", 0),
                max_price=config.get("max_price", 0),
            )

            all_properties.extend(properties)
            logger.info(
                "OTM location search complete",
                location=location_name,
                count=len(properties),
            )

        return all_properties

    async def run_all_searches(self) -> list[ScrapedProperty]:
        """Run all configured searches across all locations."""
        all_properties = []
        seen_ids = set()

        for config in OTM_SEARCH_CONFIGS:
            logger.info("Running OTM search config", config=config)
            properties = await self.search_all_locations(config)

            # Deduplicate
            for prop in properties:
                if prop.source_id not in seen_ids:
                    seen_ids.add(prop.source_id)
                    all_properties.append(prop)

        logger.info("OTM searches complete", total_unique=len(all_properties))
        return all_properties

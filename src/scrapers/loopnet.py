import asyncio
import re
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

# LoopNet UK search locations
LOOPNET_LOCATIONS = {
    "london": "london",
    "manchester": "manchester",
    "birmingham": "birmingham",
    "leeds": "leeds",
    "liverpool": "liverpool",
    "uk-wide": "united-kingdom",
}

LOOPNET_SEARCH_CONFIGS = [
    {
        "property_type": "multifamily",
        "min_price": 100000,
        "max_price": 2000000,
    },
    {
        "property_type": "residential-income",
        "min_price": 100000,
        "max_price": 2000000,
    },
]


class LoopNetScraper:
    """Scraper for LoopNet commercial property listings using Playwright."""

    BASE_URL = "https://www.loopnet.co.uk"
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
        property_type: str = "multifamily",
        min_price: int = 0,
        max_price: int = 0,
        page: int = 1,
    ) -> str:
        """Build search URL for LoopNet UK."""
        # LoopNet UK uses a different URL structure
        base = f"{self.BASE_URL}/search/{property_type}-properties/{location}/for-sale"
        params = []

        if min_price > 0:
            params.append(f"price-min={min_price}")
        if max_price > 0:
            params.append(f"price-max={max_price}")
        if page > 1:
            params.append(f"page={page}")

        if params:
            return f"{base}?{'&'.join(params)}"
        return base

    async def search(
        self,
        location: str,
        property_type: str = "multifamily",
        min_price: int = 0,
        max_price: int = 0,
        max_pages: int = 3,
    ) -> list[ScrapedProperty]:
        """Search LoopNet using Playwright browser automation."""
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
                    property_type=property_type,
                    min_price=min_price,
                    max_price=max_price,
                    page=page_num,
                )

                try:
                    logger.info("Fetching LoopNet page", url=url, page=page_num)
                    await page.goto(url, timeout=self.timeout)
                    await page.wait_for_load_state("networkidle", timeout=self.timeout)

                    # Wait for listings to load - LoopNet uses article elements
                    await page.wait_for_selector('article.placard', timeout=10000)

                    # Extract listings
                    listings = await page.query_selector_all('article.placard')
                    if not listings:
                        logger.info("No more LoopNet listings", page=page_num)
                        break

                    for listing in listings:
                        try:
                            prop = await self._parse_listing(listing)
                            if prop:
                                properties.append(prop)
                        except Exception as e:
                            logger.warning("Failed to parse LoopNet listing", error=str(e))

                except Exception as e:
                    logger.error("LoopNet page fetch failed", error=str(e), url=url)
                    break

            await browser.close()

        return properties

    async def _parse_listing(self, listing) -> Optional[ScrapedProperty]:
        """Parse a single LoopNet listing element."""
        try:
            # Extract property link and ID
            link_element = await listing.query_selector('a.placard-pseudo-link')
            if not link_element:
                link_element = await listing.query_selector('a[href*="/listing/"]')
            if not link_element:
                return None

            href = await link_element.get_attribute("href")
            if not href:
                return None

            # Extract property ID from URL
            match = re.search(r'/listing/(\d+)', href)
            if not match:
                # Try alternative pattern
                match = re.search(r'/(\d+)/?$', href)
            if not match:
                return None
            property_id = match.group(1)

            # Extract price
            price_element = await listing.query_selector('.placard-header-price, .price')
            price_text = await price_element.inner_text() if price_element else "0"
            asking_price = self._parse_price(price_text)
            if not asking_price:
                return None

            # Extract address
            address_element = await listing.query_selector('.placard-header-address, .address')
            address_text = await address_element.inner_text() if address_element else ""
            address_parts = address_text.split(", ")
            address_line1 = address_parts[0] if address_parts else address_text
            city = address_parts[-2] if len(address_parts) > 2 else (address_parts[-1] if len(address_parts) > 1 else "")
            postcode = extract_postcode(address_text) or ""

            # Extract description/summary
            desc_element = await listing.query_selector('.placard-description, .description')
            description = await desc_element.inner_text() if desc_element else ""

            # Extract title/property type
            title_element = await listing.query_selector('.placard-header-title, .property-type')
            title = await title_element.inner_text() if title_element else "Commercial Property"

            # Extract property details (units, size, etc.)
            details_element = await listing.query_selector('.placard-header-info, .property-info')
            details_text = await details_element.inner_text() if details_element else ""

            # Extract images
            images = []
            img_elements = await listing.query_selector_all('img')
            for img in img_elements:
                src = await img.get_attribute("src")
                if src and "placeholder" not in src.lower() and "logo" not in src.lower():
                    images.append(src)

            # Full text for extraction
            full_text = f"{title} {description} {details_text} {address_text}"

            # Run text extraction
            unit_result = extract_unit_count(full_text)
            tenure_result = extract_tenure(full_text)
            refurb_indicators = extract_refurb_indicators(full_text)
            red_flags = extract_red_flags(full_text)
            bedroom_breakdown = extract_bedrooms(full_text)
            floor_area_result = extract_floor_area(full_text, None)
            total_beds_result = extract_total_bedrooms(full_text)

            # Try to extract unit count from details if not found in text
            if not unit_result.value:
                unit_match = re.search(r'(\d+)\s*(?:units?|flats?|apartments?)', details_text.lower())
                if unit_match:
                    unit_result.value = int(unit_match.group(1))
                    unit_result.confidence = 0.85

            return ScrapedProperty(
                source_id=f"loopnet_{property_id}",
                source_url=f"{self.BASE_URL}{href}" if not href.startswith("http") else href,
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
                agent_name=None,
                estimated_units=unit_result.value,
                unit_confidence=unit_result.confidence,
                tenure=tenure_result.value,
                tenure_confidence=tenure_result.confidence,
                refurb_indicators=refurb_indicators,
                red_flags=red_flags,
                bedroom_breakdown=bedroom_breakdown,
                listed_date=None,
                raw_data={"source": "loopnet", "id": property_id},
                bedrooms=total_beds_result.value,
                bathrooms=None,
                floor_area_sqft=floor_area_result.sqft,
                floor_area_sqm=floor_area_result.sqm,
                floor_area_source=floor_area_result.source,
                property_type=title,
                has_floorplan=False,
            )

        except Exception as e:
            logger.warning("Error parsing LoopNet listing", error=str(e))
            return None

    def _parse_price(self, price_text: str) -> Optional[int]:
        """Parse price from text like '£250,000' or '$250,000'."""
        # Handle GBP
        match = re.search(r'£([\d,]+)', price_text)
        if match:
            return int(match.group(1).replace(',', ''))
        # Handle plain numbers
        match = re.search(r'([\d,]+)', price_text)
        if match:
            value = int(match.group(1).replace(',', ''))
            if value > 10000:  # Sanity check
                return value
        return None

    async def search_all_locations(
        self,
        config: dict,
        locations: Optional[dict] = None,
    ) -> list[ScrapedProperty]:
        """Search across all configured locations."""
        locations = locations or LOOPNET_LOCATIONS
        all_properties = []

        for location_name, location_slug in locations.items():
            logger.info("Searching LoopNet location", location=location_name)

            properties = await self.search(
                location=location_slug,
                property_type=config.get("property_type", "multifamily"),
                min_price=config.get("min_price", 0),
                max_price=config.get("max_price", 0),
            )

            all_properties.extend(properties)
            logger.info(
                "LoopNet location search complete",
                location=location_name,
                count=len(properties),
            )

        return all_properties

    async def run_all_searches(self) -> list[ScrapedProperty]:
        """Run all configured searches across all locations."""
        all_properties = []
        seen_ids = set()

        for config in LOOPNET_SEARCH_CONFIGS:
            logger.info("Running LoopNet search config", config=config)
            properties = await self.search_all_locations(config)

            # Deduplicate
            for prop in properties:
                if prop.source_id not in seen_ids:
                    seen_ids.add(prop.source_id)
                    all_properties.append(prop)

        logger.info("LoopNet searches complete", total_unique=len(all_properties))
        return all_properties

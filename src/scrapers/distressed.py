"""UK Distressed Property scraper for finding below-market-value opportunities."""
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


@dataclass
class DistressedProperty:
    """Property from UK Distressed Property list."""

    address: str
    postcode: str
    asking_price: int
    distress_type: str  # repossession, short_lease, knotweed, low_epc, etc.
    property_type: str
    bedrooms: Optional[int]
    description: str
    rightmove_url: Optional[str]
    source_url: str
    reduced_price: bool = False


# Distress categories and their impact on value
DISTRESS_CATEGORIES = {
    "repossession": {"discount_range": (15, 30), "severity": "high"},
    "short_lease": {"discount_range": (20, 50), "severity": "high"},
    "japanese_knotweed": {"discount_range": (10, 25), "severity": "medium"},
    "low_epc": {"discount_range": (5, 15), "severity": "low"},
    "poor_condition": {"discount_range": (15, 35), "severity": "high"},
    "water_damage": {"discount_range": (10, 25), "severity": "medium"},
    "fire_damage": {"discount_range": (20, 40), "severity": "high"},
    "cash_buyer": {"discount_range": (5, 15), "severity": "low"},
    "probate": {"discount_range": (10, 20), "severity": "medium"},
    "divorce": {"discount_range": (5, 15), "severity": "low"},
}


class DistressedPropertyScraper:
    """Scraper for UK Distressed Property website using Playwright."""

    BASE_URL = "https://www.ukdistressedproperty.co.uk"
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

    async def scrape_list_page(self, url: str) -> list[DistressedProperty]:
        """Scrape a UK Distressed Property list page."""
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

            try:
                await self._rate_limit()
                logger.info("Fetching distressed property list", url=url)

                await page.goto(url, timeout=self.timeout)
                await page.wait_for_load_state("networkidle", timeout=self.timeout)

                # Wait for content to load
                await page.wait_for_selector("article, .property-item, table, .entry-content", timeout=10000)

                # Try to find property listings in various formats
                # UK Distressed Property often uses tables or lists
                content = await page.content()

                # Extract from table format
                tables = await page.query_selector_all("table")
                for table in tables:
                    rows = await table.query_selector_all("tr")
                    for row in rows:
                        prop = await self._parse_table_row(row, url)
                        if prop:
                            properties.append(prop)

                # Extract from article/list format
                articles = await page.query_selector_all("article, .property-item, .listing")
                for article in articles:
                    prop = await self._parse_article(article, url)
                    if prop:
                        properties.append(prop)

                # Try to extract from main content if structured elements not found
                if not properties:
                    main_content = await page.query_selector(".entry-content, .post-content, main")
                    if main_content:
                        text = await main_content.inner_text()
                        properties = self._parse_text_content(text, url)

                logger.info("Distressed properties found", count=len(properties))

            except Exception as e:
                logger.error("Failed to scrape distressed list", error=str(e), url=url)

            await browser.close()

        return properties

    async def _parse_table_row(self, row, source_url: str) -> Optional[DistressedProperty]:
        """Parse a table row containing property data."""
        try:
            cells = await row.query_selector_all("td")
            if len(cells) < 3:
                return None

            cell_texts = []
            for cell in cells:
                text = await cell.inner_text()
                cell_texts.append(text.strip())

            # Try to extract data from cells
            address = ""
            price = 0
            distress_type = "unknown"
            property_type = ""
            bedrooms = None

            for i, text in enumerate(cell_texts):
                # Look for price
                price_match = re.search(r'£([\d,]+)', text)
                if price_match and not price:
                    price = int(price_match.group(1).replace(',', ''))
                    continue

                # Look for postcode (indicates address)
                if extract_postcode(text) and not address:
                    address = text
                    continue

                # Look for bedrooms
                bed_match = re.search(r'(\d+)\s*bed', text.lower())
                if bed_match:
                    bedrooms = int(bed_match.group(1))

                # Look for property type
                if any(t in text.lower() for t in ['house', 'flat', 'apartment', 'bungalow', 'terrace']):
                    property_type = text

                # Look for distress indicators
                text_lower = text.lower()
                for dtype, _ in DISTRESS_CATEGORIES.items():
                    if dtype.replace('_', ' ') in text_lower or dtype in text_lower:
                        distress_type = dtype
                        break

            if not address or not price:
                return None

            # Check for Rightmove link
            rightmove_link = await row.query_selector('a[href*="rightmove"]')
            rightmove_url = None
            if rightmove_link:
                rightmove_url = await rightmove_link.get_attribute("href")

            # Check for reduced price indicator
            row_text = await row.inner_text()
            reduced = "reduced" in row_text.lower() or "↓" in row_text

            return DistressedProperty(
                address=address,
                postcode=extract_postcode(address) or "",
                asking_price=price,
                distress_type=distress_type,
                property_type=property_type,
                bedrooms=bedrooms,
                description=row_text,
                rightmove_url=rightmove_url,
                source_url=source_url,
                reduced_price=reduced,
            )

        except Exception as e:
            logger.warning("Failed to parse table row", error=str(e))
            return None

    async def _parse_article(self, article, source_url: str) -> Optional[DistressedProperty]:
        """Parse an article element containing property data."""
        try:
            text = await article.inner_text()

            # Extract price
            price_match = re.search(r'£([\d,]+)', text)
            if not price_match:
                return None
            price = int(price_match.group(1).replace(',', ''))

            # Extract address (look for postcode)
            postcode = extract_postcode(text)
            if not postcode:
                return None

            # Try to get address line
            address_match = re.search(r'([^,\n]+,\s*[^,\n]+,?\s*' + re.escape(postcode) + r')', text)
            address = address_match.group(1) if address_match else postcode

            # Extract bedrooms
            bed_match = re.search(r'(\d+)\s*bed', text.lower())
            bedrooms = int(bed_match.group(1)) if bed_match else None

            # Determine property type
            property_type = "Property"
            for ptype in ['house', 'flat', 'apartment', 'bungalow', 'terrace', 'detached', 'semi-detached']:
                if ptype in text.lower():
                    property_type = ptype.title()
                    break

            # Determine distress type
            distress_type = "unknown"
            text_lower = text.lower()
            for dtype, _ in DISTRESS_CATEGORIES.items():
                if dtype.replace('_', ' ') in text_lower or dtype in text_lower:
                    distress_type = dtype
                    break

            # Check for Rightmove link
            rightmove_link = await article.query_selector('a[href*="rightmove"]')
            rightmove_url = None
            if rightmove_link:
                rightmove_url = await rightmove_link.get_attribute("href")

            reduced = "reduced" in text_lower

            return DistressedProperty(
                address=address,
                postcode=postcode,
                asking_price=price,
                distress_type=distress_type,
                property_type=property_type,
                bedrooms=bedrooms,
                description=text[:500],
                rightmove_url=rightmove_url,
                source_url=source_url,
                reduced_price=reduced,
            )

        except Exception as e:
            logger.warning("Failed to parse article", error=str(e))
            return None

    def _parse_text_content(self, text: str, source_url: str) -> list[DistressedProperty]:
        """Parse unstructured text content for property data."""
        properties = []

        # Split by common delimiters
        lines = text.split('\n')

        current_property = {}
        for line in lines:
            line = line.strip()
            if not line:
                if current_property.get('address') and current_property.get('price'):
                    prop = DistressedProperty(
                        address=current_property.get('address', ''),
                        postcode=current_property.get('postcode', ''),
                        asking_price=current_property.get('price', 0),
                        distress_type=current_property.get('distress_type', 'unknown'),
                        property_type=current_property.get('property_type', 'Property'),
                        bedrooms=current_property.get('bedrooms'),
                        description=current_property.get('description', ''),
                        rightmove_url=current_property.get('rightmove_url'),
                        source_url=source_url,
                        reduced_price=current_property.get('reduced', False),
                    )
                    properties.append(prop)
                current_property = {}
                continue

            # Extract price
            price_match = re.search(r'£([\d,]+)', line)
            if price_match:
                current_property['price'] = int(price_match.group(1).replace(',', ''))

            # Extract postcode/address
            postcode = extract_postcode(line)
            if postcode:
                current_property['postcode'] = postcode
                current_property['address'] = line

            # Extract bedrooms
            bed_match = re.search(r'(\d+)\s*bed', line.lower())
            if bed_match:
                current_property['bedrooms'] = int(bed_match.group(1))

            # Check for distress indicators
            line_lower = line.lower()
            for dtype, _ in DISTRESS_CATEGORIES.items():
                if dtype.replace('_', ' ') in line_lower:
                    current_property['distress_type'] = dtype
                    break

            # Build description
            current_property['description'] = current_property.get('description', '') + ' ' + line

            # Check for reduced
            if 'reduced' in line_lower:
                current_property['reduced'] = True

        return properties

    def to_scraped_property(self, prop: DistressedProperty) -> ScrapedProperty:
        """Convert DistressedProperty to ScrapedProperty format."""
        # Build description with distress info
        distress_info = DISTRESS_CATEGORIES.get(prop.distress_type, {})
        discount_range = distress_info.get('discount_range', (0, 0))

        description = f"{prop.description}\n\nDistress Type: {prop.distress_type.replace('_', ' ').title()}"
        if discount_range[1] > 0:
            description += f"\nTypical Discount: {discount_range[0]}-{discount_range[1]}%"
        if prop.reduced_price:
            description += "\n⚠️ PRICE REDUCED"

        # Run text extraction
        full_text = f"{prop.address} {prop.description}"
        unit_result = extract_unit_count(full_text)
        tenure_result = extract_tenure(full_text)
        refurb_indicators = extract_refurb_indicators(full_text)
        red_flags = extract_red_flags(full_text)

        # Add distress type as red flag
        red_flags.append({
            "flag": f"Distressed: {prop.distress_type.replace('_', ' ')}",
            "severity": distress_info.get('severity', 'medium'),
        })

        return ScrapedProperty(
            source_id=f"distressed_{hash(prop.address) & 0xFFFFFFFF}",
            source_url=prop.rightmove_url or prop.source_url,
            title=f"{prop.property_type} - {prop.distress_type.replace('_', ' ').title()}",
            asking_price=prop.asking_price,
            price_qualifier="Distressed",
            address_line1=prop.address,
            address_line2=None,
            city="",
            postcode=prop.postcode,
            latitude=None,
            longitude=None,
            description=description,
            images=[],
            agent_name="UK Distressed Property",
            estimated_units=unit_result.value,
            unit_confidence=unit_result.confidence,
            tenure=tenure_result.value,
            tenure_confidence=tenure_result.confidence,
            refurb_indicators=refurb_indicators,
            red_flags=red_flags,
            bedroom_breakdown=[],
            listed_date=None,
            raw_data={
                "source": "ukdistressedproperty",
                "distress_type": prop.distress_type,
                "reduced_price": prop.reduced_price,
            },
            bedrooms=prop.bedrooms,
            bathrooms=None,
            floor_area_sqft=None,
            floor_area_sqm=None,
            floor_area_source="unknown",
            property_type=prop.property_type,
            has_floorplan=False,
        )

    async def scrape_latest_list(self) -> list[ScrapedProperty]:
        """Scrape the latest distressed property list."""
        # The site typically has weekly lists
        # Try to find the latest one
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()

            await page.goto(self.BASE_URL, timeout=self.timeout)
            await page.wait_for_load_state("networkidle")

            # Find links to property lists
            links = await page.query_selector_all('a[href*="property-list"]')
            list_urls = []
            for link in links:
                href = await link.get_attribute("href")
                if href and "property-list" in href:
                    if not href.startswith("http"):
                        href = f"{self.BASE_URL}{href}"
                    list_urls.append(href)

            await browser.close()

        all_properties = []
        for url in list_urls[:3]:  # Scrape up to 3 recent lists
            props = await self.scrape_list_page(url)
            all_properties.extend([self.to_scraped_property(p) for p in props])

        # Deduplicate by address
        seen_addresses = set()
        unique_properties = []
        for prop in all_properties:
            if prop.address_line1 not in seen_addresses:
                seen_addresses.add(prop.address_line1)
                unique_properties.append(prop)

        logger.info("Distressed scraping complete", total=len(unique_properties))
        return unique_properties

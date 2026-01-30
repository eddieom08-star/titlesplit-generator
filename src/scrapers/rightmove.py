import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import uuid4

import httpx
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
    FloorAreaResult,
)

logger = structlog.get_logger()

# Search configurations for title split opportunities
SEARCH_CONFIGS = [
    {
        "keywords": "block of flats freehold",
        "property_type": "flat",
        "min_price": 100000,
        "max_price": 800000,
    },
    {
        "keywords": "investment opportunity freehold",
        "property_type": "flat",
        "min_price": 100000,
        "max_price": 800000,
    },
    {
        "keywords": "refurbishment flats",
        "property_type": "flat",
        "min_price": 100000,
        "max_price": 800000,
    },
]

# Target locations with pre-resolved location IDs
LOCATIONS = {
    "liverpool": "REGION^786",
    "manchester": "REGION^904",
    "wigan": "REGION^1290",
    "leeds": "REGION^711",
    "sheffield": "REGION^1138",
    "bradford": "REGION^181",
    "newcastle": "REGION^1852",
    "bolton": "REGION^167",
    "hull": "REGION^594",
    "middlesbrough": "REGION^933",
}


@dataclass
class ScrapedProperty:
    source_id: str
    source_url: str
    title: str
    asking_price: int
    price_qualifier: Optional[str]
    address_line1: str
    address_line2: Optional[str]
    city: str
    postcode: str
    latitude: Optional[float]
    longitude: Optional[float]
    description: str
    images: list[str]
    agent_name: Optional[str]
    estimated_units: Optional[int]
    unit_confidence: float
    tenure: str
    tenure_confidence: float
    refurb_indicators: list[dict]
    red_flags: list[dict]
    bedroom_breakdown: list[dict]
    listed_date: Optional[datetime]
    raw_data: dict
    # Additional extracted fields
    bedrooms: Optional[int] = None  # Total bedrooms from API or text
    bathrooms: Optional[int] = None  # Total bathrooms from API
    floor_area_sqft: Optional[float] = None  # Floor area in sqft
    floor_area_sqm: Optional[float] = None  # Floor area in sqm
    floor_area_source: str = "unknown"  # Where floor area came from
    property_type: Optional[str] = None  # Property type from API
    has_floorplan: bool = False  # Whether floorplan images exist
    key_features: list[str] = None  # Key features from listing

    def __post_init__(self):
        if self.key_features is None:
            self.key_features = []


class RightmoveScraper:
    """Scraper for Rightmove property listings using hidden REST API."""

    BASE_URL = "https://www.rightmove.co.uk/api/_search"
    PROPERTY_URL = "https://www.rightmove.co.uk/properties/{property_id}"
    RATE_LIMIT_SECONDS = 2.0

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self._last_request_time: Optional[float] = None

    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        if self._last_request_time:
            elapsed = asyncio.get_event_loop().time() - self._last_request_time
            if elapsed < self.RATE_LIMIT_SECONDS:
                await asyncio.sleep(self.RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    def _build_search_params(
        self,
        location_id: str,
        keywords: str = "",
        min_price: int = 0,
        max_price: int = 0,
        property_type: str = "flat",
        index: int = 0,
    ) -> dict:
        """Build search parameters for Rightmove API."""
        params = {
            "locationIdentifier": location_id,
            "numberOfPropertiesPerPage": 24,
            "radius": 0.0,
            "sortType": 6,  # Most recent
            "includeLetAgreed": "false",
            "viewType": "LIST",
            "channel": "BUY",
            "areaSizeUnit": "sqft",
            "currencyCode": "GBP",
            "index": index,
        }

        if keywords:
            params["keywords"] = keywords
        if min_price > 0:
            params["minPrice"] = min_price
        if max_price > 0:
            params["maxPrice"] = max_price
        if property_type:
            params["propertyTypes"] = property_type

        return params

    async def search(
        self,
        location_id: str,
        keywords: str = "",
        min_price: int = 0,
        max_price: int = 0,
        property_type: str = "flat",
        max_pages: int = 5,
    ) -> list[ScrapedProperty]:
        """Search Rightmove for properties matching criteria."""
        properties = []
        index = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for page in range(max_pages):
                await self._rate_limit()

                params = self._build_search_params(
                    location_id=location_id,
                    keywords=keywords,
                    min_price=min_price,
                    max_price=max_price,
                    property_type=property_type,
                    index=index,
                )

                try:
                    response = await client.get(
                        self.BASE_URL,
                        params=params,
                        headers=self._get_headers(),
                    )
                    response.raise_for_status()
                    data = response.json()

                    listings = data.get("properties", [])
                    if not listings:
                        break

                    for listing in listings:
                        try:
                            prop = self._parse_listing(listing)
                            if prop:
                                properties.append(prop)
                        except Exception as e:
                            logger.warning(
                                "Failed to parse listing",
                                error=str(e),
                                listing_id=listing.get("id"),
                            )

                    # Check if more pages exist
                    result_count = data.get("resultCount", "0")
                    result_count = int(result_count.replace(",", ""))
                    index += 24
                    if index >= result_count:
                        break

                except httpx.HTTPError as e:
                    logger.error("Search request failed", error=str(e), page=page)
                    break

        return properties

    def _get_headers(self) -> dict:
        """Get request headers to mimic browser."""
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-GB,en;q=0.9",
            "Referer": "https://www.rightmove.co.uk/",
        }

    def _parse_listing(self, data: dict) -> Optional[ScrapedProperty]:
        """Parse a single listing from API response."""
        property_id = str(data.get("id", ""))
        if not property_id:
            return None

        # Extract price
        price_data = data.get("price", {})
        asking_price = price_data.get("amount", 0)
        if not asking_price:
            return None

        # Extract address
        display_address = data.get("displayAddress", "")
        address_parts = display_address.split(", ")
        address_line1 = address_parts[0] if address_parts else display_address
        address_line2 = address_parts[1] if len(address_parts) > 1 else None
        city = address_parts[-1] if len(address_parts) > 1 else ""

        # Extract postcode from address
        postcode = extract_postcode(display_address)
        if not postcode:
            # Try from propertySubDescription or summary
            summary = data.get("summary", "")
            postcode = extract_postcode(summary) or ""

        # Extract location
        location = data.get("location", {})
        latitude = location.get("latitude")
        longitude = location.get("longitude")

        # Extract description/summary
        summary = data.get("summary", "")
        property_sub_desc = data.get("propertySubDescription", "")
        full_text = f"{summary} {property_sub_desc}".strip()

        # Extract images
        images = []
        for img in data.get("propertyImages", {}).get("images", []):
            src = img.get("srcUrl", "")
            if src:
                images.append(src)

        # Extract agent
        customer = data.get("customer", {})
        agent_name = customer.get("branchDisplayName")

        # Extract listing date
        listing_update = data.get("listingUpdate", {})
        listed_date = None
        if listing_update.get("listingUpdateDate"):
            try:
                listed_date = datetime.fromisoformat(
                    listing_update["listingUpdateDate"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        # Extract direct fields from API (more reliable than text extraction)
        api_bedrooms = data.get("bedrooms")
        api_bathrooms = data.get("bathrooms")
        property_type = data.get("propertyTypeFullDescription", "")

        # Check for floorplan availability
        floorplan_images = data.get("floorplanImages", {}).get("images", [])
        has_floorplan = len(floorplan_images) > 0

        # Initialize floor area
        floor_area_sqft = None
        floor_area_sqm = None
        floor_area_source = "unknown"

        # Run text extraction
        unit_result = extract_unit_count(full_text)
        tenure_result = extract_tenure(full_text)
        refurb_indicators = extract_refurb_indicators(full_text)
        red_flags = extract_red_flags(full_text)
        bedroom_breakdown = extract_bedrooms(full_text)

        # Extract floor area from text if not in API
        floor_area_result = extract_floor_area(full_text, api_bedrooms)
        if floor_area_result.sqft:
            floor_area_sqft = floor_area_result.sqft
            floor_area_sqm = floor_area_result.sqm
            floor_area_source = floor_area_result.source

        # Try to extract total bedrooms from text if not in API
        bedrooms = api_bedrooms
        if not bedrooms:
            total_beds_result = extract_total_bedrooms(full_text)
            if total_beds_result.value:
                bedrooms = total_beds_result.value

        return ScrapedProperty(
            source_id=property_id,
            source_url=self.PROPERTY_URL.format(property_id=property_id),
            title=property_type,
            asking_price=asking_price,
            price_qualifier=price_data.get("displayPrices", [{}])[0].get("displayPriceQualifier"),
            address_line1=address_line1,
            address_line2=address_line2,
            city=city,
            postcode=postcode,
            latitude=latitude,
            longitude=longitude,
            description=full_text,
            images=images,
            agent_name=agent_name,
            estimated_units=unit_result.value,
            unit_confidence=unit_result.confidence,
            tenure=tenure_result.value,
            tenure_confidence=tenure_result.confidence,
            refurb_indicators=refurb_indicators,
            red_flags=red_flags,
            bedroom_breakdown=bedroom_breakdown,
            listed_date=listed_date,
            raw_data=data,
            # Additional fields
            bedrooms=bedrooms,
            bathrooms=api_bathrooms,
            floor_area_sqft=floor_area_sqft,
            floor_area_sqm=floor_area_sqm,
            floor_area_source=floor_area_source,
            property_type=property_type,
            has_floorplan=has_floorplan,
        )

    async def search_all_locations(
        self,
        config: dict,
        locations: Optional[dict] = None,
    ) -> list[ScrapedProperty]:
        """Search across all configured locations."""
        locations = locations or LOCATIONS
        all_properties = []

        for location_name, location_id in locations.items():
            logger.info("Searching location", location=location_name)

            properties = await self.search(
                location_id=location_id,
                keywords=config.get("keywords", ""),
                min_price=config.get("min_price", 0),
                max_price=config.get("max_price", 0),
                property_type=config.get("property_type", "flat"),
            )

            all_properties.extend(properties)
            logger.info(
                "Location search complete",
                location=location_name,
                count=len(properties),
            )

        return all_properties

    async def run_all_searches(self) -> list[ScrapedProperty]:
        """Run all configured searches across all locations."""
        all_properties = []
        seen_ids = set()

        for config in SEARCH_CONFIGS:
            logger.info("Running search config", config=config)
            properties = await self.search_all_locations(config)

            # Deduplicate
            for prop in properties:
                if prop.source_id not in seen_ids:
                    seen_ids.add(prop.source_id)
                    all_properties.append(prop)

        logger.info("All searches complete", total_unique=len(all_properties))
        return all_properties

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger()

# In-memory cache for Land Registry results (TTL-based)
_cache: dict[str, tuple[list, datetime]] = {}
_CACHE_TTL_SECONDS = 21600  # 6 hour cache - Land Registry data updates monthly


@dataclass
class ComparableSale:
    address: str
    postcode: str
    price: int
    sale_date: datetime
    property_type: str  # F=Flat, T=Terraced, S=Semi, D=Detached
    new_build: bool
    estate_type: str  # F=Freehold, L=Leasehold
    transaction_category: str
    raw_data: dict


@dataclass
class HousePriceIndex:
    region: str
    date: datetime
    index_value: float
    average_price: int
    monthly_change: float
    annual_change: float


# Fields that require manual verification (Land Registry lookup)
MANUAL_VERIFICATION_REQUIRED = [
    "title_number",
    "registered_proprietor",
    "existing_charges",
    "restrictive_covenants",
    "easements",
    "title_plan",
]


class LandRegistryClient:
    """Client for HM Land Registry Price Paid Data."""

    # Use Linked Data API (SPARQL endpoint is unreliable)
    PPD_BASE_URL = "https://landregistry.data.gov.uk/data/ppi/transaction-record.json"

    PROPERTY_TYPES = {
        "flat": "flat-maisonette",
        "terraced": "terraced",
        "semi-detached": "semi-detached",
        "detached": "detached",
        "other": "otherPropertyType",
    }

    async def get_comparable_sales(
        self,
        postcode: str,
        property_type: str = "F",  # F=Flat
        months_back: int = 24,
        max_results: int = 50,
    ) -> list[ComparableSale]:
        """
        Fetch recent sales in the area for valuation.

        Uses Land Registry Linked Data API with caching and concurrent requests.
        """
        postcode = postcode.upper().strip()

        # Check cache first
        cache_key = f"{postcode}:{property_type}:{months_back}"
        if cache_key in _cache:
            cached_sales, cached_time = _cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < _CACHE_TTL_SECONDS:
                logger.info("Land Registry cache hit", postcode=postcode, count=len(cached_sales))
                return cached_sales[:max_results]

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months_back * 30)

        # Map property type code to API value
        prop_type_map = {"F": "flat-maisonette", "T": "terraced", "S": "semi-detached", "D": "detached"}
        property_type_value = prop_type_map.get(property_type, "flat-maisonette")

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            all_sales = []

            # Try exact postcode first
            sales = await self._fetch_sales(client, postcode, property_type_value, start_date, max_results)
            all_sales.extend(sales)
            logger.info("Land Registry exact postcode search", postcode=postcode, count=len(sales))

            # If not enough results, expand to postcode sector CONCURRENTLY
            if len(all_sales) < 10:
                postcode_sector = postcode.rsplit(" ", 1)[0] if " " in postcode else postcode[:-3]
                # Build list of nearby postcodes to search
                nearby_postcodes = [
                    f"{postcode_sector} {suffix}"
                    for suffix in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
                    if f"{postcode_sector} {suffix}" != postcode[:len(postcode_sector) + 2]
                ]
                # Fetch all concurrently instead of sequentially
                if nearby_postcodes:
                    tasks = [
                        self._fetch_sales(client, nearby, property_type_value, start_date, 10)
                        for nearby in nearby_postcodes[:5]  # Limit to 5 concurrent requests
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for result in results:
                        if isinstance(result, list):
                            all_sales.extend(result)

            # Deduplicate early to avoid unnecessary expansion
            all_sales = self._deduplicate_sales(all_sales)

            # If still not enough, try other property types CONCURRENTLY
            if len(all_sales) < 5:
                logger.info("Expanding search to all property types", postcode=postcode)
                tasks = [
                    self._fetch_sales(client, postcode, prop_type, start_date, 20)
                    for prop_type in ["terraced", "semi-detached", "detached"]
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, list):
                        all_sales.extend(result)

            # Only use unfiltered search as last resort
            if len(all_sales) < 3:
                logger.info("Searching all sales without property type filter", postcode=postcode)
                extra_sales = await self._fetch_sales_no_type(client, postcode, start_date, 30)
                all_sales.extend(extra_sales)

            # Final deduplication and sort
            unique_sales = self._deduplicate_sales(all_sales)
            unique_sales.sort(key=lambda s: s.sale_date, reverse=True)
            result = unique_sales[:max_results]

            # Cache the result
            _cache[cache_key] = (result, datetime.now())

            return result

    def _deduplicate_sales(self, sales: list[ComparableSale]) -> list[ComparableSale]:
        """Remove duplicate sales based on address, price, and date."""
        seen = set()
        unique = []
        for sale in sales:
            key = (sale.address, sale.price, sale.sale_date.date())
            if key not in seen:
                seen.add(key)
                unique.append(sale)
        return unique

    async def _fetch_sales(
        self,
        client: httpx.AsyncClient,
        postcode: str,
        property_type: str,
        min_date: datetime,
        limit: int,
    ) -> list[ComparableSale]:
        """Fetch sales from the Linked Data API."""
        try:
            # Build URL with filters
            params = {
                "propertyAddress.postcode": postcode,
                "propertyType": f"http://landregistry.data.gov.uk/def/common/{property_type}",
                "min-transactionDate": min_date.strftime("%Y-%m-%d"),
                "_pageSize": str(limit),
                "_sort": "-transactionDate",
            }

            response = await client.get(self.PPD_BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

            sales = []
            for item in data.get("result", {}).get("items", []):
                try:
                    sale = self._parse_linked_data_item(item)
                    if sale:
                        sales.append(sale)
                except Exception as e:
                    logger.warning("Failed to parse sale record", error=str(e))

            return sales

        except httpx.HTTPError as e:
            logger.warning("Land Registry API request failed", error=str(e), postcode=postcode)
            return []

    async def _fetch_sales_no_type(
        self,
        client: httpx.AsyncClient,
        postcode: str,
        min_date: datetime,  # Kept for signature compatibility but not used
        limit: int,
    ) -> list[ComparableSale]:
        """Fetch sales without property type filter OR date filter (last resort)."""
        try:
            # NO date filter - get any historical sales, sorted by date
            # Old sales are still useful when time-adjusted
            params = {
                "propertyAddress.postcode": postcode,
                "_pageSize": str(limit),
                "_sort": "-transactionDate",
            }

            response = await client.get(self.PPD_BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

            sales = []
            for item in data.get("result", {}).get("items", []):
                try:
                    sale = self._parse_linked_data_item(item)
                    if sale:
                        sales.append(sale)
                except Exception as e:
                    logger.warning("Failed to parse sale record", error=str(e))

            return sales

        except httpx.HTTPError as e:
            logger.warning("Land Registry API request failed (no type)", error=str(e), postcode=postcode)
            return []

    def _parse_linked_data_item(self, item: dict) -> Optional[ComparableSale]:
        """Parse a sale record from Linked Data API response."""
        try:
            price = item.get("pricePaid", 0)
            if not price:
                return None

            # Parse date - API returns various formats including "Fri, 12 Jan 2001"
            date_val = item.get("transactionDate")
            if isinstance(date_val, dict):
                date_str = date_val.get("_value", "")
            else:
                date_str = str(date_val) if date_val else ""

            sale_date = datetime.now()
            if date_str:
                try:
                    # Try ISO format first (YYYY-MM-DD)
                    sale_date = datetime.fromisoformat(date_str[:10])
                except ValueError:
                    try:
                        # Try human-readable format "Fri, 12 Jan 2001"
                        from email.utils import parsedate_to_datetime
                        sale_date = parsedate_to_datetime(date_str)
                    except (ValueError, TypeError):
                        try:
                            # Try alternative format "12 Jan 2001"
                            sale_date = datetime.strptime(date_str, "%d %b %Y")
                        except ValueError:
                            logger.warning("Could not parse date", date_str=date_str)

            # Parse address
            addr_obj = item.get("propertyAddress", {})
            address_parts = [
                addr_obj.get("saon", ""),
                addr_obj.get("paon", ""),
                addr_obj.get("street", ""),
                addr_obj.get("town", ""),
            ]
            address = " ".join(filter(None, address_parts)).strip()
            postcode = addr_obj.get("postcode", "")

            # Parse property type
            prop_type_obj = item.get("propertyType", {})
            prop_type_label = ""
            if isinstance(prop_type_obj, dict):
                prop_type_label = prop_type_obj.get("_about", "")
            property_type = self._parse_property_type(prop_type_label)

            # Parse estate type
            estate_obj = item.get("estateType", {})
            estate_label = ""
            if isinstance(estate_obj, dict):
                estate_label = estate_obj.get("_about", "")
            estate_type = "F" if "freehold" in estate_label.lower() else "L"

            # New build
            new_build = bool(item.get("newBuild", False))

            return ComparableSale(
                address=address,
                postcode=postcode,
                price=price,
                sale_date=sale_date,
                property_type=property_type,
                new_build=new_build,
                estate_type=estate_type,
                transaction_category="standard",
                raw_data=item,
            )
        except Exception as e:
            logger.warning("Failed to parse linked data item", error=str(e))
            return None

    def _parse_property_type(self, uri: str) -> str:
        """Parse property type from URI."""
        uri_lower = uri.lower()
        if "flat" in uri_lower or "maisonette" in uri_lower:
            return "F"
        elif "terraced" in uri_lower:
            return "T"
        elif "semi" in uri_lower:
            return "S"
        elif "detached" in uri_lower:
            return "D"
        return "O"

    async def get_postcode_average(
        self,
        postcode: str,
        property_type: str = "F",
        months_back: int = 12,
    ) -> Optional[dict]:
        """Get average price for a postcode sector."""
        sales = await self.get_comparable_sales(
            postcode=postcode,
            property_type=property_type,
            months_back=months_back,
        )

        if not sales:
            return None

        prices = [s.price for s in sales]
        return {
            "count": len(prices),
            "average": sum(prices) // len(prices),
            "median": sorted(prices)[len(prices) // 2],
            "min": min(prices),
            "max": max(prices),
            "period_months": months_back,
        }


def calculate_time_adjusted_price(
    sale_price: int,
    sale_date: datetime,
    annual_appreciation: float = 0.03,  # 3% default
) -> int:
    """
    Adjust historical sale price to current value.

    Uses simple compound appreciation - in production,
    should use UKHPI regional indices.
    """
    days_ago = (datetime.now() - sale_date).days
    years = days_ago / 365.25

    adjusted = sale_price * ((1 + annual_appreciation) ** years)
    return int(adjusted)


def calculate_price_per_sqm(
    price: int,
    floor_area_sqm: float,
) -> float:
    """Calculate price per square meter."""
    if floor_area_sqm <= 0:
        return 0.0
    return price / floor_area_sqm


def calculate_price_per_sqft(
    price: int,
    floor_area_sqm: float,
) -> float:
    """Calculate price per square foot."""
    sqft = floor_area_sqm * 10.764  # Convert sqm to sqft
    if sqft <= 0:
        return 0.0
    return price / sqft

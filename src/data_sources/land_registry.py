from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger()


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

    PPD_BASE_URL = "https://landregistry.data.gov.uk/data/ppi/transaction-record.json"
    SPARQL_ENDPOINT = "https://landregistry.data.gov.uk/app/root/qonsole/query"

    PROPERTY_TYPES = {
        "flat": "F",
        "terraced": "T",
        "semi-detached": "S",
        "detached": "D",
        "other": "O",
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

        Used for:
        - Section 5: Individual unit values (aggregate vs portfolio)
        - Section 2: Exit strategy (market evidence)
        """
        # Get the postcode sector (e.g., "L1 2" from "L1 2AB")
        postcode = postcode.upper().strip()
        postcode_sector = postcode.rsplit(" ", 1)[0] if " " in postcode else postcode[:-3]

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months_back * 30)

        # Build SPARQL query for Price Paid Data
        query = self._build_ppd_query(
            postcode_sector=postcode_sector,
            property_type=property_type,
            start_date=start_date,
            end_date=end_date,
            limit=max_results,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    self.SPARQL_ENDPOINT,
                    data={"query": query, "output": "json"},
                    headers={"Accept": "application/sparql-results+json"},
                )
                response.raise_for_status()
                data = response.json()

                sales = []
                for binding in data.get("results", {}).get("bindings", []):
                    try:
                        sale = self._parse_sale(binding)
                        if sale:
                            sales.append(sale)
                    except Exception as e:
                        logger.warning("Failed to parse sale record", error=str(e))

                return sales

            except httpx.HTTPError as e:
                logger.error("Land Registry API request failed", error=str(e))
                return []

    def _build_ppd_query(
        self,
        postcode_sector: str,
        property_type: str,
        start_date: datetime,
        end_date: datetime,
        limit: int,
    ) -> str:
        """Build SPARQL query for Price Paid Data."""
        return f"""
        PREFIX lrppi: <http://landregistry.data.gov.uk/def/ppi/>
        PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>

        SELECT ?item ?price ?date ?propertyType ?newBuild ?estateType ?address ?postcode
        WHERE {{
            ?item a lrppi:TransactionRecord ;
                  lrppi:pricePaid ?price ;
                  lrppi:transactionDate ?date ;
                  lrppi:propertyType ?propertyType ;
                  lrppi:newBuild ?newBuild ;
                  lrppi:estateType ?estateType ;
                  lrppi:propertyAddress ?addressObj .

            ?addressObj lrcommon:postcode ?postcode ;
                        lrcommon:paon ?paon .

            OPTIONAL {{ ?addressObj lrcommon:saon ?saon }}
            OPTIONAL {{ ?addressObj lrcommon:street ?street }}
            OPTIONAL {{ ?addressObj lrcommon:town ?town }}

            BIND(CONCAT(COALESCE(?saon, ""), " ", ?paon, " ", COALESCE(?street, ""), ", ", COALESCE(?town, "")) AS ?address)

            FILTER(STRSTARTS(?postcode, "{postcode_sector}"))
            FILTER(?date >= "{start_date.strftime('%Y-%m-%d')}"^^xsd:date)
            FILTER(?date <= "{end_date.strftime('%Y-%m-%d')}"^^xsd:date)
            FILTER(?propertyType = lrcommon:{self._get_property_type_uri(property_type)})
        }}
        ORDER BY DESC(?date)
        LIMIT {limit}
        """

    def _get_property_type_uri(self, type_code: str) -> str:
        """Convert property type code to URI fragment."""
        mapping = {
            "F": "flat-maisonette",
            "T": "terraced",
            "S": "semi-detached",
            "D": "detached",
            "O": "other",
        }
        return mapping.get(type_code, "flat-maisonette")

    def _parse_sale(self, binding: dict) -> Optional[ComparableSale]:
        """Parse a single sale record from SPARQL results."""
        try:
            price = int(binding.get("price", {}).get("value", 0))
            if not price:
                return None

            date_str = binding.get("date", {}).get("value", "")
            sale_date = datetime.fromisoformat(date_str) if date_str else datetime.now()

            property_type_uri = binding.get("propertyType", {}).get("value", "")
            property_type = self._parse_property_type(property_type_uri)

            new_build_uri = binding.get("newBuild", {}).get("value", "")
            new_build = "true" in new_build_uri.lower() or "new-build" in new_build_uri.lower()

            estate_type_uri = binding.get("estateType", {}).get("value", "")
            estate_type = "F" if "freehold" in estate_type_uri.lower() else "L"

            return ComparableSale(
                address=binding.get("address", {}).get("value", "").strip(),
                postcode=binding.get("postcode", {}).get("value", "").strip(),
                price=price,
                sale_date=sale_date,
                property_type=property_type,
                new_build=new_build,
                estate_type=estate_type,
                transaction_category="standard",
                raw_data=binding,
            )
        except Exception as e:
            logger.warning("Failed to parse sale", error=str(e))
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

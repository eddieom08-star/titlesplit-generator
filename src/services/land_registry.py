"""Land Registry client for UK House Price Index and Price Paid Data."""
from typing import Optional
from datetime import datetime, timedelta

import httpx
import structlog

logger = structlog.get_logger()


class LandRegistryClient:
    """
    Client for HM Land Registry open data.

    Two main data sources:
    1. UK House Price Index (UKHPI) - Regional price indices
    2. Price Paid Data (PPD) - Individual transaction records
    """

    SPARQL_ENDPOINT = "https://landregistry.data.gov.uk/landregistry/query"

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_regional_hpi(
        self,
        region: str,
        months_back: int = 24
    ) -> list[dict]:
        """
        Get House Price Index data for a region.

        Returns official government price index and average prices.
        """
        start_date = (datetime.now() - timedelta(days=months_back * 30)).strftime("%Y-%m")

        sparql_query = f"""
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX ukhpi: <http://landregistry.data.gov.uk/def/ukhpi/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        SELECT ?date ?avgPrice ?index ?salesVolume
        WHERE {{
            ?obs ukhpi:refRegion ?region .
            ?region rdfs:label "{region}"@en .
            ?obs ukhpi:refMonth ?date .
            ?obs ukhpi:averagePrice ?avgPrice .
            ?obs ukhpi:housePriceIndex ?index .
            OPTIONAL {{ ?obs ukhpi:salesVolume ?salesVolume }}
            FILTER (?date >= "{start_date}"^^xsd:gYearMonth)
        }}
        ORDER BY DESC(?date)
        LIMIT 24
        """

        try:
            response = await self.client.get(
                self.SPARQL_ENDPOINT,
                params={"query": sparql_query, "output": "json"}
            )
            response.raise_for_status()
            return self._parse_sparql_results(response.json())
        except Exception as e:
            logger.error("HPI lookup failed", region=region, error=str(e))
            return []

    async def get_price_paid_comparables(
        self,
        postcode_district: str,
        property_type: str = "F",
        months_back: int = 24
    ) -> list[dict]:
        """
        Get actual transaction records from Price Paid Data.

        Args:
            postcode_district: e.g., "L4", "M14"
            property_type: F=Flat, T=Terraced, S=Semi, D=Detached
            months_back: How many months of data to retrieve

        Returns:
            List of comparable sales with address, price, date, etc.
        """
        start_date = (datetime.now() - timedelta(days=months_back * 30)).strftime("%Y-%m-%d")

        sparql_query = f"""
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX ppi: <http://landregistry.data.gov.uk/def/ppi/>
        PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>

        SELECT ?paon ?saon ?street ?postcode ?price ?date ?newBuild ?estateType
        WHERE {{
            ?txn ppi:propertyAddress ?addr .
            ?addr lrcommon:postcode ?postcode .
            FILTER(STRSTARTS(?postcode, "{postcode_district}"))

            ?txn ppi:pricePaid ?price .
            ?txn ppi:transactionDate ?date .
            ?txn ppi:propertyType ppi:{property_type} .
            ?txn ppi:newBuild ?newBuild .
            ?txn ppi:estateType ?estateType .

            ?addr lrcommon:paon ?paon .
            OPTIONAL {{ ?addr lrcommon:saon ?saon }}
            ?addr lrcommon:street ?street .

            FILTER(?date >= "{start_date}"^^xsd:date)
        }}
        ORDER BY DESC(?date)
        LIMIT 100
        """

        try:
            response = await self.client.get(
                self.SPARQL_ENDPOINT,
                params={"query": sparql_query, "output": "json"}
            )
            response.raise_for_status()
            return self._parse_ppd_results(response.json())
        except Exception as e:
            logger.error("PPD lookup failed", postcode=postcode_district, error=str(e))
            return []

    async def get_flat_sales_summary(
        self,
        postcode_district: str,
        months_back: int = 18
    ) -> dict:
        """
        Get flat sales split by Freehold vs Leasehold.

        Returns:
            Summary with leasehold/freehold split and average prices.
        """
        comps = await self.get_price_paid_comparables(
            postcode_district=postcode_district,
            property_type="F",
            months_back=months_back
        )

        if not comps:
            return {
                "leasehold_count": 0,
                "freehold_count": 0,
                "leasehold_average": None,
                "freehold_average": None,
                "total_sales": 0,
            }

        leasehold = [c for c in comps if c.get("estate_type") == "L"]
        freehold = [c for c in comps if c.get("estate_type") == "F"]

        return {
            "leasehold_count": len(leasehold),
            "freehold_count": len(freehold),
            "leasehold_average": sum(c["price"] for c in leasehold) // len(leasehold) if leasehold else None,
            "freehold_average": sum(c["price"] for c in freehold) // len(freehold) if freehold else None,
            "total_sales": len(comps),
        }

    def _parse_sparql_results(self, data: dict) -> list[dict]:
        """Parse SPARQL JSON results."""
        results = []
        for binding in data.get("results", {}).get("bindings", []):
            results.append({
                k: v.get("value")
                for k, v in binding.items()
            })
        return results

    def _parse_ppd_results(self, data: dict) -> list[dict]:
        """Parse PPD SPARQL results into clean format."""
        results = []
        for binding in data.get("results", {}).get("bindings", []):
            saon = binding.get("saon", {}).get("value", "")
            paon = binding.get("paon", {}).get("value", "")
            street = binding.get("street", {}).get("value", "")
            address = f"{saon} {paon} {street}".strip()

            estate_uri = binding.get("estateType", {}).get("value", "")
            estate_type = "L" if "leasehold" in estate_uri.lower() else "F"

            results.append({
                "address": address,
                "postcode": binding.get("postcode", {}).get("value"),
                "price": int(float(binding.get("price", {}).get("value", 0))),
                "date": binding.get("date", {}).get("value"),
                "new_build": binding.get("newBuild", {}).get("value") == "true",
                "estate_type": estate_type,
            })
        return results

    @staticmethod
    def postcode_to_region(postcode: str) -> str:
        """Map postcode to region name for HPI lookup."""
        postcode_regions = {
            "L": "Liverpool",
            "M": "Manchester",
            "B": "Birmingham",
            "LS": "Leeds",
            "S": "Sheffield",
            "NE": "Newcastle upon Tyne",
            "BS": "Bristol",
            "NG": "Nottingham",
            "LE": "Leicester",
            "CF": "Cardiff",
            "EH": "Edinburgh",
            "G": "Glasgow",
            "SW": "London",
            "SE": "London",
            "E": "London",
            "N": "London",
            "W": "London",
            "NW": "London",
            "EC": "London",
            "WC": "London",
        }

        prefix = postcode.split()[0] if " " in postcode else postcode[:2]

        for code, region in postcode_regions.items():
            if prefix.startswith(code):
                return region

        return "England"

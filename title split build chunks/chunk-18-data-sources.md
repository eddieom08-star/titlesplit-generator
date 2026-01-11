## CHUNK 18: Data Source Integration

### 18.1 Data Source Overview

The application integrates three primary data sources to produce lender-grade valuations:

| Source | Type | Cost | Data Provided | Update Frequency |
|--------|------|------|---------------|------------------|
| **PropertyData.co.uk** | Commercial API | £28-150/month | Valuations, comparables, £/sqft, yields, floor areas | Real-time |
| **PropertyMarketIntel.com** | Commercial API | Subscription | Comparables, market research, deal analysis | Real-time |
| **Land Registry UKHPI** | Government (Free) | Free | House price indices, regional trends | Monthly |
| **Land Registry Price Paid** | Government (Free) | Free | Actual transaction prices | Monthly |
| **EPC Open Data** | Government (Free) | Free | Floor areas, energy ratings, property age | Monthly |

### 18.2 PropertyData API Integration

**API Base URL:** `https://api.propertydata.co.uk`
**Authentication:** API key in query parameter
**Rate Limit:** 1 credit per request (most endpoints)
**Documentation:** https://propertydata.co.uk/api/documentation

```python
# src/data_sources/property_data.py

from typing import Optional, List
from pydantic import BaseModel
import httpx


class PropertyDataClient:
    """
    Client for PropertyData.co.uk API.
    
    Key endpoints for title split GDV:
    - /valuation-sale: Automated property valuations
    - /sold-prices: Recent sold prices with EPC matching
    - /sold-prices-per-sqf: £/sqft sold data
    - /prices-per-sqf: Current asking £/sqft
    - /floor-areas: Floor area data from EPCs
    - /yields: Local yield calculations
    - /growth: Price growth trends
    - /development-gdv: GDV calculations
    """
    
    BASE_URL = "https://api.propertydata.co.uk"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def get_valuation(
        self,
        postcode: str,
        property_type: str = "flat",
        bedrooms: Optional[int] = None,
        internal_area: Optional[int] = None,  # sqft
        finish_quality: str = "average",  # below_average, average, above_average, high
        outdoor_space: str = "none",  # none, balcony_terrace, garden, large_garden
        parking: str = "none",  # none, off_street, garage, multiple
    ) -> dict:
        """
        Get automated valuation for a property.
        
        This is the PRIMARY method for individual unit valuations.
        
        Returns:
        {
            "result": "GBP",
            "result_int": 185000,
            "price_per_sqft": 285,
            "confidence": "medium",  # low, medium, high
            "valuation_range": {"low": 175000, "high": 195000},
            "data_points": 23,
            "radius": 0.3
        }
        """
        params = {
            "key": self.api_key,
            "postcode": postcode,
            "property_type": property_type,
            "finish_quality": finish_quality,
            "outdoor_space": outdoor_space,
            "parking": parking,
        }
        if bedrooms:
            params["bedrooms"] = bedrooms
        if internal_area:
            params["internal_area"] = internal_area
        
        response = await self.client.get(
            f"{self.BASE_URL}/valuation-sale",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    async def get_sold_prices(
        self,
        postcode: str,
        property_type: str = "flat",
        max_age: int = 12,  # months
        bedrooms: Optional[int] = None,
    ) -> dict:
        """
        Get recent sold prices in the area.
        
        Returns actual Land Registry transactions with EPC data matched.
        
        Returns:
        {
            "postcode": "L4 0TH",
            "data": [
                {
                    "address": "Flat 1, 123 Example Street",
                    "price": 85000,
                    "date": "2025-06-15",
                    "type": "flat",
                    "bedrooms": 2,
                    "sqft": 650,
                    "price_per_sqft": 131,
                    "new_build": false
                },
                ...
            ],
            "average": 92000,
            "average_per_sqft": 142,
            "data_points": 15,
            "radius": 0.5
        }
        """
        params = {
            "key": self.api_key,
            "postcode": postcode,
            "type": property_type,
            "max_age": max_age,
        }
        if bedrooms:
            params["bedrooms"] = bedrooms
        
        response = await self.client.get(
            f"{self.BASE_URL}/sold-prices",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    async def get_sold_prices_per_sqft(
        self,
        postcode: str,
        property_type: str = "flat",
        bedrooms: Optional[int] = None,
    ) -> dict:
        """
        Get £/sqft statistics for sold properties.
        
        Critical for lender presentations - shows market rate per sqft.
        
        Returns:
        {
            "average": 185,  # £/sqft
            "70pc_range": {"low": 155, "high": 215},
            "data_points": 45,
            "radius": 0.4
        }
        """
        params = {
            "key": self.api_key,
            "postcode": postcode,
            "type": property_type,
        }
        if bedrooms:
            params["bedrooms"] = bedrooms
        
        response = await self.client.get(
            f"{self.BASE_URL}/sold-prices-per-sqf",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    async def get_floor_areas(
        self,
        postcode: str,
        property_type: str = "flat",
    ) -> dict:
        """
        Get floor area statistics from EPC data.
        
        Useful when listing doesn't specify sqft.
        
        Returns:
        {
            "average_sqft": 680,
            "median_sqft": 650,
            "80pc_range": {"low": 450, "high": 850},
            "data_points": 120
        }
        """
        params = {
            "key": self.api_key,
            "postcode": postcode,
            "property_type": property_type,
        }
        
        response = await self.client.get(
            f"{self.BASE_URL}/floor-areas",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    async def get_yields(
        self,
        postcode: str,
    ) -> dict:
        """
        Get local yield statistics.
        
        Used for investment analysis and lender ICR calculations.
        
        Returns:
        {
            "yield": 6.2,  # Gross yield %
            "80pc_range": {"low": 5.1, "high": 7.8},
            "average_rent_pcm": 650,
            "average_price": 125000,
            "data_points": 35
        }
        """
        params = {
            "key": self.api_key,
            "postcode": postcode,
        }
        
        response = await self.client.get(
            f"{self.BASE_URL}/yields",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    async def get_price_growth(
        self,
        postcode: str,
    ) -> dict:
        """
        Get historical price growth data.
        
        Important for lender presentations showing market trajectory.
        
        Returns:
        {
            "1_year": 2.3,  # % change
            "3_year": 8.5,
            "5_year": 15.2,
            "10_year": 45.0,
            "data_source": "Land Registry HPI"
        }
        """
        params = {
            "key": self.api_key,
            "postcode": postcode,
        }
        
        response = await self.client.get(
            f"{self.BASE_URL}/growth",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    async def get_development_gdv(
        self,
        postcode: str,
        units: List[dict],  # [{"type": "flat", "bedrooms": 2, "sqft": 650}, ...]
    ) -> dict:
        """
        Calculate GDV for a development.
        
        PropertyData's built-in GDV calculator.
        
        Returns:
        {
            "total_gdv": 450000,
            "units": [
                {"type": "flat", "bedrooms": 2, "value": 115000},
                ...
            ],
            "average_per_sqft": 165,
            "confidence": "medium"
        }
        """
        # Note: This endpoint may require specific formatting
        # Check PropertyData docs for exact parameters
        pass
```

### 18.3 Land Registry UKHPI Integration

**API Base URL:** `https://landregistry.data.gov.uk`
**Authentication:** None required
**Format:** SPARQL queries or direct CSV download
**Documentation:** https://landregistry.data.gov.uk/app/ukhpi/doc

```python
# src/data_sources/land_registry.py

import httpx
from typing import Optional
from datetime import datetime, timedelta


class LandRegistryClient:
    """
    Client for HM Land Registry open data.
    
    Two main data sources:
    1. UK House Price Index (UKHPI) - Regional price indices
    2. Price Paid Data (PPD) - Individual transaction records
    """
    
    UKHPI_SPARQL = "https://landregistry.data.gov.uk/landregistry/query"
    PPD_API = "https://landregistry.data.gov.uk/data/ppi"
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def get_regional_hpi(
        self,
        region: str,  # e.g., "Liverpool", "Manchester"
        months_back: int = 24
    ) -> dict:
        """
        Get House Price Index data for a region.
        
        Returns official government price index and average prices.
        
        SPARQL Query for regional data.
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
        
        response = await self.client.get(
            self.UKHPI_SPARQL,
            params={
                "query": sparql_query,
                "output": "json"
            }
        )
        response.raise_for_status()
        return self._parse_sparql_results(response.json())
    
    async def get_price_paid_comparables(
        self,
        postcode_district: str,  # e.g., "L4", "M14"
        property_type: str = "F",  # F=Flat, T=Terraced, S=Semi, D=Detached
        months_back: int = 24
    ) -> list:
        """
        Get actual transaction records from Price Paid Data.
        
        This is the gold standard for comparable evidence.
        
        Returns:
        [
            {
                "address": "FLAT 2, 45 EXAMPLE ROAD",
                "postcode": "L4 2AB",
                "price": 85000,
                "date": "2025-03-15",
                "property_type": "F",
                "new_build": false,
                "estate_type": "L"  # L=Leasehold, F=Freehold
            },
            ...
        ]
        """
        # Using the PPD linked data API
        start_date = (datetime.now() - timedelta(days=months_back * 30)).strftime("%Y-%m-%d")
        
        sparql_query = f"""
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX ppi: <http://landregistry.data.gov.uk/def/ppi/>
        PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>

        SELECT ?address ?postcode ?price ?date ?propertyType ?newBuild ?estateType
        WHERE {{
            ?txn ppi:propertyAddress ?addr .
            ?addr lrcommon:postcode ?postcode .
            FILTER(STRSTARTS(?postcode, "{postcode_district}"))
            
            ?txn ppi:pricePaid ?price .
            ?txn ppi:transactionDate ?date .
            ?txn ppi:propertyType ?propertyType .
            ?txn ppi:newBuild ?newBuild .
            ?txn ppi:estateType ?estateType .
            
            ?addr lrcommon:paon ?paon .
            OPTIONAL {{ ?addr lrcommon:saon ?saon }}
            ?addr lrcommon:street ?street .
            
            BIND(CONCAT(COALESCE(?saon, ""), " ", ?paon, " ", ?street) AS ?address)
            
            FILTER(?propertyType = ppi:{property_type})
            FILTER(?date >= "{start_date}"^^xsd:date)
        }}
        ORDER BY DESC(?date)
        LIMIT 100
        """
        
        response = await self.client.get(
            "https://landregistry.data.gov.uk/landregistry/query",
            params={
                "query": sparql_query,
                "output": "json"
            }
        )
        response.raise_for_status()
        return self._parse_ppd_results(response.json())
    
    async def get_flat_sales_with_estate_type(
        self,
        postcode_district: str,
        months_back: int = 12
    ) -> dict:
        """
        Get flat sales split by Freehold vs Leasehold.
        
        Critical for understanding the premium leasehold flats
        achieve vs the block price.
        
        Returns:
        {
            "leasehold_flats": {
                "count": 45,
                "average_price": 95000,
                "median_price": 92000
            },
            "freehold_flats": {
                "count": 3,
                "average_price": 280000,  # Usually blocks
                "median_price": 265000
            },
            "premium_percentage": 18.5  # Leasehold individual vs block per-unit
        }
        """
        # This requires analysing the PPD data
        pass
    
    def _parse_sparql_results(self, data: dict) -> list:
        """Parse SPARQL JSON results."""
        results = []
        for binding in data.get("results", {}).get("bindings", []):
            results.append({
                k: v.get("value") 
                for k, v in binding.items()
            })
        return results
    
    def _parse_ppd_results(self, data: dict) -> list:
        """Parse PPD SPARQL results into clean format."""
        results = []
        for binding in data.get("results", {}).get("bindings", []):
            results.append({
                "address": binding.get("address", {}).get("value"),
                "postcode": binding.get("postcode", {}).get("value"),
                "price": int(binding.get("price", {}).get("value", 0)),
                "date": binding.get("date", {}).get("value"),
                "property_type": binding.get("propertyType", {}).get("value", "").split("/")[-1],
                "new_build": binding.get("newBuild", {}).get("value") == "true",
                "estate_type": binding.get("estateType", {}).get("value", "").split("/")[-1],
            })
        return results
```

### 18.4 PropertyMarketIntel Integration

**Note:** PropertyMarketIntel offers an Enterprise/API tier. Contact them for API access.

For MVP, we can use PropertyData as the primary commercial source. PropertyMarketIntel can be added later for additional validation or as a fallback.

```python
# src/data_sources/property_market_intel.py

class PropertyMarketIntelClient:
    """
    Client for PropertyMarketIntel.com API.
    
    Features:
    - Comparables and valuations
    - Deal profitability calculator
    - Market research data
    - 64+ data sources including ONS and Land Registry
    
    Note: API access requires Enterprise subscription.
    Contact: https://www.propertymarketintel.com/enterprise-api
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Implementation depends on their API specification
        pass
```

---


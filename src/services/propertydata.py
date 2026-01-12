"""PropertyData API client for UK property valuations and data."""
import asyncio
from typing import Optional
from dataclasses import dataclass

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


@dataclass
class PropertyValuation:
    """Property valuation result from PropertyData API."""
    postcode: str
    property_type: str
    estimated_value: Optional[int]
    value_low: Optional[int]
    value_high: Optional[int]
    confidence: str
    rental_estimate: Optional[int]
    rental_low: Optional[int]
    rental_high: Optional[int]
    sold_prices_nearby: list[dict]
    epc_rating: Optional[str]
    planning_applications: list[dict]


class PropertyDataClient:
    """Client for PropertyData.co.uk API."""

    BASE_URL = "https://api.propertydata.co.uk"
    RATE_LIMIT_SECONDS = 1.0  # Respect rate limits

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.property_data_api_key
        self._last_request_time: Optional[float] = None

    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        if self._last_request_time:
            elapsed = asyncio.get_event_loop().time() - self._last_request_time
            if elapsed < self.RATE_LIMIT_SECONDS:
                await asyncio.sleep(self.RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _request(self, endpoint: str, params: dict) -> dict:
        """Make API request with rate limiting."""
        await self._rate_limit()

        params["key"] = self.api_key

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/{endpoint}",
                params=params,
            )

            if response.status_code == 401:
                logger.error("PropertyData API: Invalid API key")
                raise ValueError("Invalid PropertyData API key")

            if response.status_code == 429:
                logger.warning("PropertyData API: Rate limited")
                raise ValueError("PropertyData API rate limit exceeded")

            if response.status_code != 200:
                logger.error(
                    "PropertyData API error",
                    status=response.status_code,
                    response=response.text[:200],
                )
                raise ValueError(f"PropertyData API error: {response.status_code}")

            return response.json()

    async def get_valuation(
        self,
        postcode: str,
        property_type: str = "flat",
        bedrooms: Optional[int] = None,
        internal_area: Optional[int] = None,
    ) -> Optional[PropertyValuation]:
        """
        Get property valuation estimate using sold prices data.

        Args:
            postcode: UK postcode
            property_type: flat, terraced, semi-detached, detached
            bedrooms: Number of bedrooms (optional)
            internal_area: Internal area in sqft (optional)
        """
        try:
            # Use sold-prices endpoint as primary valuation source
            params = {
                "postcode": postcode.replace(" ", ""),
            }

            data = await self._request("sold-prices", params)

            if data.get("status") != "success":
                logger.warning("Sold prices lookup returned non-success", postcode=postcode)
                return None

            result = data.get("data", {})
            raw_data = result.get("raw_data", [])

            # Filter for flats only if property_type is flat
            if property_type == "flat":
                flat_sales = [s for s in raw_data if s.get("type") == "flat"]
                if flat_sales:
                    prices = [s["price"] for s in flat_sales]
                    avg_price = sum(prices) // len(prices)
                    prices_sorted = sorted(prices)
                    low_price = prices_sorted[0] if prices_sorted else None
                    high_price = prices_sorted[-1] if prices_sorted else None
                else:
                    avg_price = result.get("average")
                    range_70 = result.get("70pc_range", [None, None])
                    low_price = range_70[0]
                    high_price = range_70[1]
            else:
                avg_price = result.get("average")
                range_70 = result.get("70pc_range", [None, None])
                low_price = range_70[0]
                high_price = range_70[1]

            # Determine confidence based on data points
            points = result.get("points_analysed", 0)
            if points >= 20:
                confidence = "high"
            elif points >= 10:
                confidence = "medium"
            else:
                confidence = "low"

            return PropertyValuation(
                postcode=postcode,
                property_type=property_type,
                estimated_value=avg_price,
                value_low=low_price,
                value_high=high_price,
                confidence=confidence,
                rental_estimate=None,
                rental_low=None,
                rental_high=None,
                sold_prices_nearby=raw_data[:10],
                epc_rating=None,
                planning_applications=[],
            )

        except Exception as e:
            logger.error("Valuation lookup failed", postcode=postcode, error=str(e))
            return None

    async def get_sold_prices(
        self,
        postcode: str,
        property_type: str = "flat",
        max_age_months: int = 24,
    ) -> list[dict]:
        """
        Get recent sold prices near a postcode.

        Returns list of sold properties with price, date, address.
        """
        try:
            params = {
                "postcode": postcode.replace(" ", ""),
                "property_type": property_type,
                "max_age": max_age_months,
            }

            data = await self._request("sold-prices", params)

            sales = data.get("result", {}).get("prices", [])

            return [
                {
                    "price": sale.get("price"),
                    "date": sale.get("date"),
                    "address": sale.get("address"),
                    "property_type": sale.get("property_type"),
                }
                for sale in sales[:10]  # Limit to 10 most recent
            ]

        except Exception as e:
            logger.error("Sold prices lookup failed", postcode=postcode, error=str(e))
            return []

    async def get_sold_prices_per_sqf(
        self,
        postcode: str,
        max_age_months: int = 18,
    ) -> Optional[dict]:
        """
        Get sold prices with square footage data (from EPC matching).

        Returns Land Registry data enriched with EPC sqft info.
        """
        try:
            params = {
                "postcode": postcode.replace(" ", ""),
                "max_age": max_age_months,
            }

            data = await self._request("sold-prices-per-sqf", params)

            if data.get("status") != "success":
                return None

            return data.get("data", {})

        except Exception as e:
            logger.error("Sold prices per sqf lookup failed", postcode=postcode, error=str(e))
            return None

    async def get_rental_estimate(
        self,
        postcode: str,
        property_type: str = "flat",
        bedrooms: int = 2,
    ) -> Optional[dict]:
        """
        Get rental valuation estimate.

        Returns monthly rental estimate with range.
        """
        try:
            params = {
                "postcode": postcode.replace(" ", ""),
                "property_type": property_type,
                "bedrooms": bedrooms,
            }

            data = await self._request("valuation-rent", params)

            result = data.get("result", {})

            return {
                "estimate": result.get("estimate"),
                "lower": result.get("lower"),
                "upper": result.get("upper"),
                "confidence": result.get("confidence", "low"),
            }

        except Exception as e:
            logger.error("Rental estimate failed", postcode=postcode, error=str(e))
            return None

    async def get_planning(
        self,
        postcode: str,
        radius_meters: int = 500,
    ) -> list[dict]:
        """
        Get planning applications near a postcode.

        Useful for identifying development activity in the area.
        """
        try:
            params = {
                "postcode": postcode.replace(" ", ""),
                "radius": radius_meters,
            }

            data = await self._request("planning", params)

            applications = data.get("result", {}).get("applications", [])

            return [
                {
                    "reference": app.get("reference"),
                    "description": app.get("description"),
                    "status": app.get("status"),
                    "decision_date": app.get("decision_date"),
                    "address": app.get("address"),
                }
                for app in applications[:20]
            ]

        except Exception as e:
            logger.error("Planning lookup failed", postcode=postcode, error=str(e))
            return []

    async def get_full_property_data(
        self,
        postcode: str,
        property_type: str = "flat",
        bedrooms: Optional[int] = None,
    ) -> PropertyValuation:
        """
        Get comprehensive property data including valuation, sold prices, rentals.

        Combines multiple API calls for full picture.
        """
        # Run requests in parallel where possible
        valuation_task = self.get_valuation(postcode, property_type, bedrooms)
        sold_prices_task = self.get_sold_prices(postcode, property_type)
        rental_task = self.get_rental_estimate(postcode, property_type, bedrooms or 2)

        valuation, sold_prices, rental = await asyncio.gather(
            valuation_task,
            sold_prices_task,
            rental_task,
        )

        # Build combined result
        if valuation:
            valuation.sold_prices_nearby = sold_prices
            if rental:
                valuation.rental_estimate = rental.get("estimate")
                valuation.rental_low = rental.get("lower")
                valuation.rental_high = rental.get("upper")
            return valuation

        # Fallback if valuation failed
        return PropertyValuation(
            postcode=postcode,
            property_type=property_type,
            estimated_value=None,
            value_low=None,
            value_high=None,
            confidence="none",
            rental_estimate=rental.get("estimate") if rental else None,
            rental_low=rental.get("lower") if rental else None,
            rental_high=rental.get("upper") if rental else None,
            sold_prices_nearby=sold_prices,
            epc_rating=None,
            planning_applications=[],
        )


async def estimate_unit_values(
    postcode: str,
    units: list[dict],
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    Estimate values for individual units in a block.

    Args:
        postcode: Property postcode
        units: List of unit dicts with 'bedrooms' key
        api_key: PropertyData API key (optional, uses settings if not provided)

    Returns:
        List of units with estimated values added
    """
    client = PropertyDataClient(api_key)

    enriched_units = []
    for unit in units:
        bedrooms = unit.get("bedrooms", 2)

        valuation = await client.get_valuation(
            postcode=postcode,
            property_type="flat",
            bedrooms=bedrooms,
        )

        enriched_unit = unit.copy()
        if valuation:
            enriched_unit["estimated_value"] = valuation.estimated_value
            enriched_unit["value_low"] = valuation.value_low
            enriched_unit["value_high"] = valuation.value_high
            enriched_unit["value_confidence"] = valuation.confidence

        enriched_units.append(enriched_unit)

    return enriched_units


async def calculate_title_split_potential(
    postcode: str,
    asking_price: int,
    num_units: int,
    avg_bedrooms: int = 2,
    api_key: Optional[str] = None,
) -> dict:
    """
    Calculate potential title split returns with comprehensive data.

    Args:
        postcode: Property postcode
        asking_price: Current asking price of the block
        num_units: Number of units in the block
        avg_bedrooms: Average bedrooms per unit

    Returns:
        Dict with financial analysis, Land Registry data, and EPC info
    """
    client = PropertyDataClient(api_key)

    # Get sold prices with sqft data (includes EPC matching)
    sold_prices_sqf = await client.get_sold_prices_per_sqf(postcode)

    # Get basic sold prices as fallback
    valuation = await client.get_valuation(
        postcode=postcode,
        property_type="flat",
        bedrooms=avg_bedrooms,
    )

    if not valuation or not valuation.estimated_value:
        return {
            "status": "insufficient_data",
            "asking_price": asking_price,
            "num_units": num_units,
            "message": "Could not retrieve valuation data for this postcode",
        }

    unit_value = valuation.estimated_value
    total_separated_value = unit_value * num_units
    gross_uplift = total_separated_value - asking_price

    # Estimate costs (per framework)
    cost_per_unit = 3500  # Typical title split cost
    total_costs = cost_per_unit * num_units

    net_uplift = gross_uplift - total_costs
    net_per_unit = net_uplift // num_units if num_units > 0 else 0

    # Get comparable flat sales from Land Registry
    comparable_sales = []
    avg_price_per_sqf = None
    if sold_prices_sqf:
        flat_sales = [s for s in sold_prices_sqf.get("raw_data", []) if s.get("type") == "flat"]
        comparable_sales = flat_sales[:5]  # Top 5 comparables
        if flat_sales:
            sqf_prices = [s["price_per_sqf"] for s in flat_sales if s.get("price_per_sqf")]
            if sqf_prices:
                avg_price_per_sqf = sum(sqf_prices) // len(sqf_prices)

    return {
        "status": "success",
        "asking_price": asking_price,
        "num_units": num_units,
        "estimated_unit_value": unit_value,
        "unit_value_low": valuation.value_low,
        "unit_value_high": valuation.value_high,
        "unit_value_confidence": valuation.confidence,
        "total_separated_value": total_separated_value,
        "gross_uplift": gross_uplift,
        "gross_uplift_percent": round((gross_uplift / asking_price) * 100, 1) if asking_price > 0 else 0,
        "estimated_costs": total_costs,
        "net_uplift": net_uplift,
        "net_per_unit": net_per_unit,
        "meets_threshold": net_per_unit >= 2000,  # Framework minimum
        "recommendation": "proceed" if net_per_unit >= 5000 else "review" if net_per_unit >= 2000 else "decline",
        # Land Registry / EPC data
        "avg_price_per_sqf": avg_price_per_sqf,
        "comparable_sales": comparable_sales,
    }

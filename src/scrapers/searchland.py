"""Searchland API client for UK property data and opportunities."""
import asyncio
import os
from dataclasses import dataclass, field
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
)
from src.scrapers.rightmove import ScrapedProperty

logger = structlog.get_logger()


# Target locations with coordinates for Searchland searches
SEARCHLAND_LOCATIONS = {
    "liverpool": {"lat": 53.4084, "lng": -2.9916, "radius_km": 15},
    "manchester": {"lat": 53.4808, "lng": -2.2426, "radius_km": 15},
    "leeds": {"lat": 53.8008, "lng": -1.5491, "radius_km": 15},
    "sheffield": {"lat": 53.3811, "lng": -1.4701, "radius_km": 15},
    "bradford": {"lat": 53.7960, "lng": -1.7594, "radius_km": 10},
    "newcastle": {"lat": 54.9783, "lng": -1.6178, "radius_km": 15},
    "hull": {"lat": 53.7676, "lng": -0.3274, "radius_km": 10},
    "middlesbrough": {"lat": 54.5742, "lng": -1.2350, "radius_km": 10},
    "birmingham": {"lat": 52.4862, "lng": -1.8904, "radius_km": 15},
    "nottingham": {"lat": 52.9548, "lng": -1.1581, "radius_km": 15},
}


@dataclass
class SearchlandTitle:
    """Land Registry title data from Searchland."""

    title_number: str
    tenure: str  # freehold or leasehold
    address: str
    postcode: Optional[str]
    latitude: float
    longitude: float
    plot_area_sqm: Optional[float]
    property_class: Optional[str]
    date_registered: Optional[datetime]
    price_paid: Optional[int]
    owner_name: Optional[str]
    owner_type: Optional[str]  # private, company, etc.
    raw_data: dict = field(default_factory=dict)


@dataclass
class SearchlandPlanning:
    """Planning application data from Searchland."""

    reference: str
    description: str
    status: str
    decision: Optional[str]
    address: str
    postcode: Optional[str]
    latitude: float
    longitude: float
    application_type: str
    submitted_date: Optional[datetime]
    decision_date: Optional[datetime]
    lpa_name: str
    raw_data: dict = field(default_factory=dict)


@dataclass
class SearchlandOpportunity:
    """Combined opportunity data from Searchland APIs."""

    source_id: str
    address: str
    postcode: str
    latitude: float
    longitude: float
    opportunity_type: str  # title_split, planning_gain, hmo_conversion, etc.
    title_data: Optional[SearchlandTitle] = None
    planning_data: list[SearchlandPlanning] = field(default_factory=list)
    epc_rating: Optional[str] = None
    sold_prices: list[dict] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    score: float = 0.0
    notes: list[str] = field(default_factory=list)


class SearchlandScraper:
    """Client for Searchland property data APIs."""

    BASE_URL = "https://api.searchland.co.uk/v1"
    RATE_LIMIT_SECONDS = 0.5  # API is fast

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        self.api_key = api_key or os.getenv("SEARCHLAND_API_KEY")
        if not self.api_key:
            raise ValueError("SEARCHLAND_API_KEY required")
        self.timeout = timeout
        self._last_request_time: Optional[float] = None

    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        if self._last_request_time:
            elapsed = asyncio.get_event_loop().time() - self._last_request_time
            if elapsed < self.RATE_LIMIT_SECONDS:
                await asyncio.sleep(self.RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    def _get_headers(self) -> dict:
        """Get request headers with auth."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> dict:
        """Make authenticated API request."""
        await self._rate_limit()

        url = f"{self.BASE_URL}{endpoint}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                params=params,
                json=json_data,
            )
            response.raise_for_status()
            return response.json()

    async def search_titles(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
        tenure_filter: Optional[str] = None,  # freehold, leasehold
        page: int = 1,
        per_page: int = 100,
    ) -> list[SearchlandTitle]:
        """Search for Land Registry titles in an area."""
        try:
            data = await self._request(
                method="GET",
                endpoint="/titles/search",
                params={
                    "lat": latitude,
                    "lng": longitude,
                    "radius": radius_km * 1000,  # API expects meters
                    "tenure": tenure_filter,
                    "page": page,
                    "perPage": per_page,
                },
            )

            titles = []
            for item in data.get("data", []):
                title = self._parse_title(item)
                if title:
                    titles.append(title)

            logger.info(
                "Searchland titles fetched",
                count=len(titles),
                lat=latitude,
                lng=longitude,
            )
            return titles

        except httpx.HTTPError as e:
            logger.error("Searchland title search failed", error=str(e))
            return []

    async def search_planning(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 100,
    ) -> list[SearchlandPlanning]:
        """Search for planning applications in an area."""
        try:
            # Build geometry for search
            geometry = {
                "type": "Point",
                "coordinates": [longitude, latitude],
            }

            data = await self._request(
                method="POST",
                endpoint="/planning_applications/search",
                json_data={
                    "geometry": geometry,
                    "radius": radius_km * 1000,
                    "status": status,
                    "page": page,
                    "perPage": per_page,
                },
            )

            applications = []
            for item in data.get("data", []):
                app = self._parse_planning(item)
                if app:
                    applications.append(app)

            logger.info(
                "Searchland planning fetched",
                count=len(applications),
                lat=latitude,
                lng=longitude,
            )
            return applications

        except httpx.HTTPError as e:
            logger.error("Searchland planning search failed", error=str(e))
            return []

    async def get_price_paid(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 0.5,
    ) -> list[dict]:
        """Get sold prices in an area."""
        try:
            data = await self._request(
                method="GET",
                endpoint="/price_paid/",
                params={
                    "lat": latitude,
                    "lng": longitude,
                    "radius": radius_km * 1000,
                },
            )
            return data.get("data", [])

        except httpx.HTTPError as e:
            logger.error("Searchland price paid failed", error=str(e))
            return []

    async def get_epc(
        self,
        latitude: float,
        longitude: float,
    ) -> Optional[dict]:
        """Get EPC data for a location."""
        try:
            data = await self._request(
                method="GET",
                endpoint="/epc/search",
                params={
                    "lat": latitude,
                    "lng": longitude,
                    "radius": 50,  # 50 meters
                },
            )
            results = data.get("data", [])
            return results[0] if results else None

        except httpx.HTTPError as e:
            logger.error("Searchland EPC failed", error=str(e))
            return None

    async def get_constraints(
        self,
        title_number: str,
    ) -> list[str]:
        """Get planning constraints for a title."""
        try:
            data = await self._request(
                method="GET",
                endpoint="/constraints/check_title",
                params={"title_number": title_number},
            )
            return data.get("data", {}).get("constraints", [])

        except httpx.HTTPError as e:
            logger.error("Searchland constraints failed", error=str(e))
            return []

    async def search_shlaa(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
    ) -> list[dict]:
        """Search Strategic Housing Land Availability Assessment sites."""
        try:
            data = await self._request(
                method="GET",
                endpoint="/shlaa/",
                params={
                    "lat": latitude,
                    "lng": longitude,
                    "radius": radius_km * 1000,
                },
            )
            return data.get("data", [])

        except httpx.HTTPError as e:
            logger.error("Searchland SHLAA failed", error=str(e))
            return []

    async def search_allocations(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
    ) -> list[dict]:
        """Search site allocations in local plans."""
        try:
            data = await self._request(
                method="GET",
                endpoint="/allocation/",
                params={
                    "lat": latitude,
                    "lng": longitude,
                    "radius": radius_km * 1000,
                },
            )
            return data.get("data", [])

        except httpx.HTTPError as e:
            logger.error("Searchland allocations failed", error=str(e))
            return []

    def _parse_title(self, data: dict) -> Optional[SearchlandTitle]:
        """Parse title data from API response."""
        try:
            title_number = data.get("title_number")
            if not title_number:
                return None

            # Parse date
            date_registered = None
            if data.get("date_registered"):
                try:
                    date_registered = datetime.fromisoformat(
                        data["date_registered"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            return SearchlandTitle(
                title_number=title_number,
                tenure=data.get("tenure", "unknown"),
                address=data.get("address", ""),
                postcode=extract_postcode(data.get("address", "")),
                latitude=data.get("latitude", 0),
                longitude=data.get("longitude", 0),
                plot_area_sqm=data.get("plot_area"),
                property_class=data.get("property_class"),
                date_registered=date_registered,
                price_paid=data.get("price_paid"),
                owner_name=data.get("owner_name"),
                owner_type=data.get("owner_type"),
                raw_data=data,
            )
        except Exception as e:
            logger.warning("Failed to parse title", error=str(e))
            return None

    def _parse_planning(self, data: dict) -> Optional[SearchlandPlanning]:
        """Parse planning application from API response."""
        try:
            reference = data.get("reference")
            if not reference:
                return None

            # Parse dates
            submitted_date = None
            decision_date = None
            if data.get("submitted_date"):
                try:
                    submitted_date = datetime.fromisoformat(
                        data["submitted_date"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass
            if data.get("decision_date"):
                try:
                    decision_date = datetime.fromisoformat(
                        data["decision_date"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            return SearchlandPlanning(
                reference=reference,
                description=data.get("description", ""),
                status=data.get("status", ""),
                decision=data.get("decision"),
                address=data.get("address", ""),
                postcode=extract_postcode(data.get("address", "")),
                latitude=data.get("latitude", 0),
                longitude=data.get("longitude", 0),
                application_type=data.get("application_type", ""),
                submitted_date=submitted_date,
                decision_date=decision_date,
                lpa_name=data.get("lpa_name", ""),
                raw_data=data,
            )
        except Exception as e:
            logger.warning("Failed to parse planning", error=str(e))
            return None

    async def find_title_split_opportunities(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
    ) -> list[SearchlandOpportunity]:
        """Find potential title split opportunities - freehold blocks of flats."""
        opportunities = []

        # Get freehold titles in area
        titles = await self.search_titles(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            tenure_filter="freehold",
        )

        for title in titles:
            # Look for indicators of multi-unit properties
            address_lower = title.address.lower()
            is_potential = any(
                keyword in address_lower
                for keyword in ["flat", "flats", "apartment", "block", "court", "house"]
            )

            if not is_potential and title.plot_area_sqm:
                # Larger plots might have multiple dwellings
                is_potential = title.plot_area_sqm > 200

            if is_potential:
                # Get additional data
                sold_prices = await self.get_price_paid(
                    latitude=title.latitude,
                    longitude=title.longitude,
                    radius_km=0.1,
                )
                epc_data = await self.get_epc(
                    latitude=title.latitude,
                    longitude=title.longitude,
                )
                constraints = await self.get_constraints(title.title_number)

                # Score the opportunity
                score = self._score_title_split_opportunity(
                    title=title,
                    sold_prices=sold_prices,
                    constraints=constraints,
                )

                notes = []
                if title.plot_area_sqm and title.plot_area_sqm > 500:
                    notes.append(f"Large plot: {title.plot_area_sqm:.0f} sqm")
                if "flat" in address_lower or "flats" in address_lower:
                    notes.append("Address indicates flats")
                if title.owner_type == "company":
                    notes.append("Company owned")

                opportunity = SearchlandOpportunity(
                    source_id=f"searchland_{title.title_number}",
                    address=title.address,
                    postcode=title.postcode or "",
                    latitude=title.latitude,
                    longitude=title.longitude,
                    opportunity_type="title_split",
                    title_data=title,
                    epc_rating=epc_data.get("current_rating") if epc_data else None,
                    sold_prices=sold_prices,
                    constraints=constraints,
                    score=score,
                    notes=notes,
                )
                opportunities.append(opportunity)

        # Sort by score
        opportunities.sort(key=lambda x: x.score, reverse=True)

        logger.info(
            "Title split opportunities found",
            count=len(opportunities),
            lat=latitude,
            lng=longitude,
        )
        return opportunities

    async def find_planning_opportunities(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
    ) -> list[SearchlandOpportunity]:
        """Find properties with planning potential."""
        opportunities = []

        # Get approved planning applications
        planning = await self.search_planning(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            status="approved",
        )

        # Get SHLAA sites (strategic housing land)
        shlaa_sites = await self.search_shlaa(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
        )

        # Get allocated sites
        allocations = await self.search_allocations(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
        )

        # Process planning applications
        for app in planning:
            desc_lower = app.description.lower()
            # Look for conversion or development applications
            is_opportunity = any(
                keyword in desc_lower
                for keyword in [
                    "conversion",
                    "flats",
                    "residential",
                    "change of use",
                    "subdivision",
                    "hmo",
                ]
            )

            if is_opportunity:
                opportunity = SearchlandOpportunity(
                    source_id=f"searchland_planning_{app.reference}",
                    address=app.address,
                    postcode=app.postcode or "",
                    latitude=app.latitude,
                    longitude=app.longitude,
                    opportunity_type="planning_gain",
                    planning_data=[app],
                    score=0.7 if app.decision == "approved" else 0.5,
                    notes=[f"Planning: {app.description[:100]}"],
                )
                opportunities.append(opportunity)

        # Process SHLAA sites
        for site in shlaa_sites:
            opportunity = SearchlandOpportunity(
                source_id=f"searchland_shlaa_{site.get('id', uuid4().hex[:8])}",
                address=site.get("address", ""),
                postcode=extract_postcode(site.get("address", "")) or "",
                latitude=site.get("latitude", 0),
                longitude=site.get("longitude", 0),
                opportunity_type="development_land",
                score=0.6,
                notes=[f"SHLAA site: {site.get('description', '')[:100]}"],
            )
            opportunities.append(opportunity)

        # Process allocations
        for alloc in allocations:
            opportunity = SearchlandOpportunity(
                source_id=f"searchland_alloc_{alloc.get('id', uuid4().hex[:8])}",
                address=alloc.get("address", ""),
                postcode=extract_postcode(alloc.get("address", "")) or "",
                latitude=alloc.get("latitude", 0),
                longitude=alloc.get("longitude", 0),
                opportunity_type="allocated_site",
                score=0.65,
                notes=[f"Allocated: {alloc.get('description', '')[:100]}"],
            )
            opportunities.append(opportunity)

        opportunities.sort(key=lambda x: x.score, reverse=True)

        logger.info(
            "Planning opportunities found",
            count=len(opportunities),
            lat=latitude,
            lng=longitude,
        )
        return opportunities

    def _score_title_split_opportunity(
        self,
        title: SearchlandTitle,
        sold_prices: list[dict],
        constraints: list[str],
    ) -> float:
        """Score a title split opportunity 0-1."""
        score = 0.5  # Base score

        # Freehold is essential
        if title.tenure == "freehold":
            score += 0.2

        # Larger plots are better
        if title.plot_area_sqm:
            if title.plot_area_sqm > 1000:
                score += 0.15
            elif title.plot_area_sqm > 500:
                score += 0.1
            elif title.plot_area_sqm > 200:
                score += 0.05

        # Multiple sold prices suggest multiple units
        if len(sold_prices) > 2:
            score += 0.1

        # Company ownership often means investment property
        if title.owner_type == "company":
            score += 0.05

        # Constraints reduce score
        if constraints:
            score -= 0.05 * min(len(constraints), 3)

        return max(0.0, min(1.0, score))

    def opportunity_to_scraped_property(
        self,
        opportunity: SearchlandOpportunity,
    ) -> ScrapedProperty:
        """Convert Searchland opportunity to ScrapedProperty format."""
        title = opportunity.title_data

        # Build description from notes
        description = " | ".join(opportunity.notes)
        if title:
            if title.plot_area_sqm:
                description += f" | Plot: {title.plot_area_sqm:.0f} sqm"
            if title.owner_name:
                description += f" | Owner: {title.owner_name}"

        # Estimate units from sold prices
        estimated_units = len(opportunity.sold_prices) if opportunity.sold_prices else None

        return ScrapedProperty(
            source_id=opportunity.source_id,
            source_url=f"https://searchland.co.uk/map?lat={opportunity.latitude}&lng={opportunity.longitude}",
            title=opportunity.opportunity_type.replace("_", " ").title(),
            asking_price=0,  # No asking price from land registry
            price_qualifier=None,
            address_line1=opportunity.address,
            address_line2=None,
            city="",
            postcode=opportunity.postcode,
            latitude=opportunity.latitude,
            longitude=opportunity.longitude,
            description=description,
            images=[],
            agent_name=None,
            estimated_units=estimated_units,
            unit_confidence=0.5 if estimated_units else 0.0,
            tenure=title.tenure if title else "unknown",
            tenure_confidence=0.9 if title else 0.0,
            refurb_indicators=[],
            red_flags=[{"flag": c, "severity": "medium"} for c in opportunity.constraints],
            bedroom_breakdown=[],
            listed_date=None,
            raw_data={
                "source": "searchland",
                "opportunity_type": opportunity.opportunity_type,
                "score": opportunity.score,
                "title_number": title.title_number if title else None,
            },
            property_type=opportunity.opportunity_type,
            has_floorplan=False,
        )

    async def search_all_locations(
        self,
        locations: Optional[dict] = None,
        opportunity_types: list[str] = None,
    ) -> list[SearchlandOpportunity]:
        """Search all configured locations for opportunities."""
        locations = locations or SEARCHLAND_LOCATIONS
        opportunity_types = opportunity_types or ["title_split", "planning"]
        all_opportunities = []

        for location_name, coords in locations.items():
            logger.info("Searching Searchland location", location=location_name)

            if "title_split" in opportunity_types:
                title_opps = await self.find_title_split_opportunities(
                    latitude=coords["lat"],
                    longitude=coords["lng"],
                    radius_km=coords.get("radius_km", 10),
                )
                all_opportunities.extend(title_opps)

            if "planning" in opportunity_types:
                planning_opps = await self.find_planning_opportunities(
                    latitude=coords["lat"],
                    longitude=coords["lng"],
                    radius_km=coords.get("radius_km", 10),
                )
                all_opportunities.extend(planning_opps)

            logger.info(
                "Searchland location complete",
                location=location_name,
                opportunities=len(all_opportunities),
            )

        # Deduplicate by source_id
        seen_ids = set()
        unique_opportunities = []
        for opp in all_opportunities:
            if opp.source_id not in seen_ids:
                seen_ids.add(opp.source_id)
                unique_opportunities.append(opp)

        unique_opportunities.sort(key=lambda x: x.score, reverse=True)

        logger.info(
            "Searchland search complete",
            total_unique=len(unique_opportunities),
        )
        return unique_opportunities

    async def run_all_searches(self) -> list[ScrapedProperty]:
        """Run all searches and return as ScrapedProperty format."""
        opportunities = await self.search_all_locations()

        return [
            self.opportunity_to_scraped_property(opp)
            for opp in opportunities
        ]

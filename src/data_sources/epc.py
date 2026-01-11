import base64
import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


@dataclass
class EPCRecord:
    lmk_key: str
    address: str
    postcode: str
    current_rating: str  # A-G
    current_score: int
    potential_rating: str
    potential_score: int
    floor_area: float  # sqm
    property_type: str  # Flat, Maisonette, House, etc
    built_form: str  # Detached, Semi-Detached, Mid-Terrace, Enclosed End-Terrace
    construction_age_band: Optional[str]
    transaction_type: Optional[str]  # rental, marketed sale, etc
    lodgement_date: datetime
    raw_data: dict


class EPCClient:
    """Client for UK EPC Open Data API."""

    BASE_URL = "https://epc.opendatacommunities.org/api/v1/domestic/search"

    def __init__(self, email: Optional[str] = None, api_key: Optional[str] = None):
        settings = get_settings()
        self.email = email or "your-email@example.com"  # Replace with settings
        self.api_key = api_key or settings.property_data_api_key
        self._auth_header = self._create_auth_header()

    def _create_auth_header(self) -> str:
        """Create base64 encoded auth header."""
        credentials = f"{self.email}:{self.api_key}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def _get_headers(self) -> dict:
        return {
            "Authorization": self._auth_header,
            "Accept": "application/json",
        }

    async def search_by_postcode(self, postcode: str) -> list[EPCRecord]:
        """Fetch all EPC certificates at a postcode."""
        # Normalize postcode
        postcode = postcode.upper().replace(" ", "")
        postcode = f"{postcode[:-3]} {postcode[-3:]}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    self.BASE_URL,
                    params={"postcode": postcode, "size": 100},
                    headers=self._get_headers(),
                )

                if response.status_code == 401:
                    logger.error("EPC API authentication failed")
                    return []

                if response.status_code == 404:
                    logger.info("No EPCs found for postcode", postcode=postcode)
                    return []

                response.raise_for_status()
                data = response.json()

                records = []
                for row in data.get("rows", []):
                    try:
                        record = self._parse_record(row)
                        if record:
                            records.append(record)
                    except Exception as e:
                        logger.warning("Failed to parse EPC record", error=str(e))

                return records

            except httpx.HTTPError as e:
                logger.error("EPC API request failed", error=str(e), postcode=postcode)
                return []

    def _parse_record(self, data: dict) -> Optional[EPCRecord]:
        """Parse a single EPC record from API response."""
        try:
            lodgement_date = datetime.strptime(
                data.get("lodgement-date", ""), "%Y-%m-%d"
            )
        except ValueError:
            lodgement_date = datetime.now()

        return EPCRecord(
            lmk_key=data.get("lmk-key", ""),
            address=data.get("address", ""),
            postcode=data.get("postcode", ""),
            current_rating=data.get("current-energy-rating", ""),
            current_score=int(data.get("current-energy-efficiency", 0) or 0),
            potential_rating=data.get("potential-energy-rating", ""),
            potential_score=int(data.get("potential-energy-efficiency", 0) or 0),
            floor_area=float(data.get("total-floor-area", 0) or 0),
            property_type=data.get("property-type", ""),
            built_form=data.get("built-form", ""),
            construction_age_band=data.get("construction-age-band"),
            transaction_type=data.get("transaction-type"),
            lodgement_date=lodgement_date,
            raw_data=data,
        )

    async def match_epcs_to_property(
        self,
        postcode: str,
        address_hint: str,
        similarity_threshold: float = 0.5,
    ) -> list[EPCRecord]:
        """
        Match EPCs to a specific building.

        Strategy:
        1. Fetch all EPCs at postcode
        2. Filter by address similarity (fuzzy match)
        3. Deduplicate (keep latest per unit)
        4. Return matched records
        """
        all_epcs = await self.search_by_postcode(postcode)
        if not all_epcs:
            return []

        # Normalize the address hint for matching
        hint_normalized = self._normalize_address(address_hint)

        # Filter by address similarity
        matched = []
        for epc in all_epcs:
            epc_normalized = self._normalize_address(epc.address)
            similarity = SequenceMatcher(None, hint_normalized, epc_normalized).ratio()

            if similarity >= similarity_threshold:
                matched.append(epc)

        # Deduplicate - keep latest per unit address
        latest_by_unit = {}
        for epc in matched:
            unit_key = self._normalize_unit_address(epc.address)
            if unit_key not in latest_by_unit or epc.lodgement_date > latest_by_unit[unit_key].lodgement_date:
                latest_by_unit[unit_key] = epc

        return list(latest_by_unit.values())

    def _normalize_address(self, address: str) -> str:
        """Normalize address for comparison."""
        address = address.lower()
        # Remove common noise
        address = re.sub(r'\b(flat|apartment|apt|unit)\b', '', address)
        address = re.sub(r'[^\w\s]', '', address)
        address = re.sub(r'\s+', ' ', address).strip()
        return address

    def _normalize_unit_address(self, address: str) -> str:
        """
        Normalize unit address for deduplication.
        Handles: Flat 1, Flat 1A, 1, First Floor Flat, etc.
        """
        address = address.lower().strip()

        # Extract unit identifier
        patterns = [
            r'flat\s*(\d+[a-z]?)',
            r'apartment\s*(\d+[a-z]?)',
            r'unit\s*(\d+[a-z]?)',
            r'^(\d+[a-z]?)\s',
            r'(\d+[a-z]?)\s+\w+\s+street',
        ]

        for pattern in patterns:
            match = re.search(pattern, address)
            if match:
                return f"unit_{match.group(1)}"

        # Fallback - use first part of address
        return address.split(',')[0].strip()


def validate_unit_count_from_epcs(
    epcs: list[EPCRecord],
    claimed_units: int,
) -> tuple[int, float]:
    """
    Cross-validate unit count from EPC records.

    Returns: (validated_count, confidence_score)
    """
    if not epcs:
        return claimed_units, 0.50

    # Count unique unit addresses
    unique_units = set()
    client = EPCClient()  # Just for the normalize method
    for epc in epcs:
        normalized = client._normalize_unit_address(epc.address)
        unique_units.add(normalized)

    epc_count = len(unique_units)

    if epc_count == claimed_units:
        return claimed_units, 0.95
    elif epc_count > claimed_units:
        return epc_count, 0.90
    elif epc_count > 0:
        return claimed_units, 0.60  # Discrepancy - needs review
    else:
        return claimed_units, 0.50


def calculate_avg_epc_rating(epcs: list[EPCRecord]) -> tuple[str, float]:
    """Calculate average EPC rating from records."""
    if not epcs:
        return "", 0.0

    rating_scores = {"A": 7, "B": 6, "C": 5, "D": 4, "E": 3, "F": 2, "G": 1}
    score_ratings = {v: k for k, v in rating_scores.items()}

    total_score = 0
    count = 0
    for epc in epcs:
        if epc.current_rating in rating_scores:
            total_score += rating_scores[epc.current_rating]
            count += 1

    if count == 0:
        return "", 0.0

    avg_score = total_score / count
    # Round to nearest rating
    rounded = round(avg_score)
    rounded = max(1, min(7, rounded))

    return score_ratings[rounded], count / len(epcs)


def calculate_total_floor_area(epcs: list[EPCRecord]) -> float:
    """Calculate total floor area from EPC records."""
    return sum(epc.floor_area for epc in epcs if epc.floor_area > 0)


def assess_refurbishment_opportunity(epcs: list[EPCRecord]) -> dict:
    """Assess refurbishment opportunity based on EPC ratings."""
    if not epcs:
        return {"opportunity": False, "score": 0, "details": []}

    poor_ratings = ["D", "E", "F", "G"]
    poor_count = sum(1 for epc in epcs if epc.current_rating in poor_ratings)
    total = len(epcs)

    details = []
    for epc in epcs:
        if epc.current_rating in poor_ratings:
            improvement = epc.potential_score - epc.current_score
            details.append({
                "address": epc.address,
                "current": epc.current_rating,
                "potential": epc.potential_rating,
                "improvement_points": improvement,
            })

    score = (poor_count / total * 100) if total > 0 else 0

    return {
        "opportunity": poor_count > total * 0.5,  # More than 50% poor
        "score": score,
        "poor_count": poor_count,
        "total": total,
        "details": details,
    }

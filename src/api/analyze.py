"""API endpoint for manual URL analysis."""
import re
from typing import Optional
from uuid import uuid4
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
import httpx
import structlog

from src.database import AsyncSessionLocal
from src.models.property import Property
from src.scrapers.extractors import (
    extract_unit_count,
    extract_tenure,
    extract_refurb_indicators,
    extract_postcode,
)
from src.analysis.screening import initial_screen
from src.services.propertydata import PropertyDataClient, calculate_title_split_potential

logger = structlog.get_logger()
router = APIRouter(prefix="/analyze", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    url: str
    notes: Optional[str] = None


class AnalyzeResponse(BaseModel):
    id: str
    title: str
    price: int
    city: str
    postcode: str
    estimated_units: Optional[int]
    tenure: str
    opportunity_score: int
    recommendation: str
    analysis_notes: list[str]
    source_url: str


@router.post("", response_model=AnalyzeResponse)
async def analyze_url(request: AnalyzeRequest):
    """
    Analyze a property URL and return quick assessment.

    Supports:
    - Rightmove URLs
    - Zoopla URLs
    - Flexi-Agent auction URLs
    - OnTheMarket URLs
    """
    url = request.url.strip()
    logger.info("Analyzing URL", url=url)

    try:
        # Determine source and fetch data
        if "rightmove.co.uk" in url:
            property_data = await fetch_rightmove(url)
        elif "zoopla.co.uk" in url:
            property_data = await fetch_zoopla(url)
        elif "flexi-agent" in url:
            property_data = await fetch_flexi_agent(url)
        elif "onthemarket.com" in url:
            property_data = await fetch_onthemarket(url)
        else:
            # Generic fetch - try to extract what we can
            property_data = await fetch_generic(url)

        if not property_data:
            raise HTTPException(status_code=400, detail="Could not extract property data from URL")

        # Check if property with this URL already exists
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(Property).where(Property.source_url == url)
            )
            existing_property = result.scalar_one_or_none()

        if existing_property:
            # Update existing property with fresh data
            temp_property = existing_property
            temp_property.title = property_data.get("title", temp_property.title)
            temp_property.asking_price = property_data.get("price", temp_property.asking_price)
            temp_property.address_line1 = property_data.get("address", temp_property.address_line1)
            if property_data.get("city"):
                temp_property.city = property_data.get("city")
            if property_data.get("postcode"):
                temp_property.postcode = property_data.get("postcode")
            if property_data.get("units"):
                temp_property.estimated_units = property_data.get("units")
            if property_data.get("tenure") and property_data.get("tenure") != "unknown":
                temp_property.tenure = property_data.get("tenure")
            logger.info("Updating existing property", id=str(temp_property.id), url=url)
        else:
            # Create new property
            temp_property = Property(
                id=uuid4(),
                source="manual",
                source_id=f"manual-{uuid4().hex[:8]}",
                source_url=url,
                title=property_data.get("title", "Unknown Property"),
                asking_price=property_data.get("price", 0),
                address_line1=property_data.get("address", ""),
                city=property_data.get("city", ""),
                postcode=property_data.get("postcode", ""),
                estimated_units=property_data.get("units"),
                tenure=property_data.get("tenure", "unknown"),
                status="pending",
                first_seen=datetime.utcnow(),
            )

        if temp_property.estimated_units and temp_property.estimated_units > 0:
            temp_property.price_per_unit = temp_property.asking_price // temp_property.estimated_units

        # Run screening
        screening = initial_screen(temp_property)

        # Build analysis notes
        notes = []
        if screening.rejections:
            notes.extend([f"Issue: {r}" for r in screening.rejections])
        if screening.warnings:
            notes.extend([f"Warning: {w}" for w in screening.warnings])
        if not notes:
            notes.append("No major issues detected")

        # Determine recommendation
        if screening.score >= 70:
            recommendation = "proceed"
        elif screening.score >= 50:
            recommendation = "review"
        else:
            recommendation = "decline"

        # Save or update property in database
        async with AsyncSessionLocal() as session:
            temp_property.opportunity_score = screening.score
            if screening.passes:
                temp_property.status = "pending_enrichment"
            else:
                temp_property.status = "rejected"
                temp_property.rejection_reasons = {"screening_rejections": screening.rejections}

            if existing_property:
                # Merge the detached object back into session
                temp_property = await session.merge(temp_property)
                logger.info("Updated existing property", id=str(temp_property.id), passes=screening.passes)
            else:
                session.add(temp_property)
                logger.info("Created new property", id=str(temp_property.id), passes=screening.passes)

            await session.commit()
            await session.refresh(temp_property)

        return AnalyzeResponse(
            id=str(temp_property.id),
            title=temp_property.title,
            price=temp_property.asking_price,
            city=temp_property.city or "Unknown",
            postcode=temp_property.postcode or "",
            estimated_units=temp_property.estimated_units,
            tenure=temp_property.tenure,
            opportunity_score=screening.score,
            recommendation=recommendation,
            analysis_notes=notes,
            source_url=url,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Analysis failed", error=str(e), url=url)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


async def fetch_rightmove(url: str) -> dict:
    """Fetch property data from Rightmove URL."""
    # Extract property ID from URL
    match = re.search(r'/properties/(\d+)', url)
    if not match:
        match = re.search(r'propertyId=(\d+)', url)
    if not match:
        raise HTTPException(status_code=400, detail="Could not extract Rightmove property ID")

    property_id = match.group(1)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try the API endpoint
        api_url = f"https://www.rightmove.co.uk/api/_search?propertyId={property_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        }

        try:
            response = await client.get(api_url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return parse_rightmove_data(data)
        except Exception:
            pass

        # Fallback: scrape the page
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not fetch Rightmove page")

        return parse_rightmove_html(response.text, url)


def parse_rightmove_data(data: dict) -> dict:
    """Parse Rightmove API response."""
    prop = data.get("propertyData", data)

    price = 0
    if "prices" in prop:
        price = prop["prices"].get("primaryPrice", 0)
    elif "price" in prop:
        price = prop["price"].get("amount", 0)

    address = prop.get("address", {})
    display_address = address.get("displayAddress", "")

    # Combine ALL available text fields for analysis
    text_parts = [
        prop.get("propertySubDescription", ""),
        prop.get("summary", ""),
        prop.get("text", {}).get("description", ""),
        prop.get("keyFeatures", ""),
    ]
    # Handle keyFeatures if it's a list
    if isinstance(prop.get("keyFeatures"), list):
        text_parts.append(" ".join(prop.get("keyFeatures", [])))

    text = " ".join(filter(None, text_parts))
    logger.debug("Parsing Rightmove data", text_length=len(text), text_preview=text[:200])

    units = extract_unit_count(text)
    tenure = extract_tenure(text)
    postcode = extract_postcode(display_address) or ""

    return {
        "title": prop.get("propertyTypeFullDescription", "Property"),
        "price": price,
        "address": display_address,
        "city": address.get("outcode", "").split()[0] if address.get("outcode") else "",
        "postcode": postcode,
        "units": units.value,
        "tenure": tenure.value,
        "description": text,  # Include full description for further analysis
    }


def parse_rightmove_html(html: str, url: str) -> dict:
    """Parse Rightmove HTML page."""
    # Extract price
    price_match = re.search(r'£([\d,]+)', html)
    price = int(price_match.group(1).replace(',', '')) if price_match else 0

    # Extract title
    title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    title = title_match.group(1).strip() if title_match else "Property"

    # Extract address
    address_match = re.search(r'<address[^>]*>([^<]+)</address>', html)
    address = address_match.group(1).strip() if address_match else ""

    # Extract postcode
    postcode = extract_postcode(html) or ""

    # Extract key features section
    key_features_text = ""
    key_features_match = re.search(
        r'Key features.*?<ul[^>]*>(.*?)</ul>',
        html, re.IGNORECASE | re.DOTALL
    )
    if key_features_match:
        # Extract text from list items
        features = re.findall(r'<li[^>]*>([^<]+)</li>', key_features_match.group(1))
        key_features_text = " ".join(features)

    # Extract property description section
    description_text = ""
    desc_match = re.search(
        r'(?:property description|about this property).*?<div[^>]*>(.*?)</div>',
        html, re.IGNORECASE | re.DOTALL
    )
    if desc_match:
        # Strip HTML tags
        description_text = re.sub(r'<[^>]+>', ' ', desc_match.group(1))

    # Combine all text for analysis
    full_text = f"{title} {key_features_text} {description_text} {html}"
    logger.debug("Parsing Rightmove HTML", key_features=key_features_text[:100] if key_features_text else "none")

    # Extract units and tenure from full text
    units = extract_unit_count(full_text)
    tenure = extract_tenure(full_text)

    # Try to get city from address
    city = ""
    if address:
        parts = address.split(',')
        if len(parts) >= 2:
            city = parts[-2].strip()

    return {
        "title": title,
        "price": price,
        "address": address,
        "city": city,
        "postcode": postcode,
        "units": units.value,
        "tenure": tenure.value,
        "description": f"{key_features_text} {description_text}".strip(),
    }


async def fetch_zoopla(url: str) -> dict:
    """Fetch property data from Zoopla URL."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not fetch Zoopla page")

        html = response.text

        # Extract price
        price_match = re.search(r'£([\d,]+)', html)
        price = int(price_match.group(1).replace(',', '')) if price_match else 0

        # Extract title
        title_match = re.search(r'"headline":"([^"]+)"', html)
        title = title_match.group(1) if title_match else "Property"

        # Extract address
        address_match = re.search(r'"displayAddress":"([^"]+)"', html)
        address = address_match.group(1) if address_match else ""

        postcode = extract_postcode(html) or ""
        units = extract_unit_count(html)
        tenure = extract_tenure(html)

        city = ""
        if address:
            parts = address.split(',')
            if len(parts) >= 2:
                city = parts[-2].strip()

        return {
            "title": title,
            "price": price,
            "address": address,
            "city": city,
            "postcode": postcode,
            "units": units.value,
            "tenure": tenure.value,
        }


async def fetch_flexi_agent(url: str) -> dict:
    """Fetch property data from Flexi-Agent auction URL."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not fetch Flexi-Agent page")

        html = response.text

        # Extract guide price
        price_match = re.search(r'Guide Price[:\s]*£([\d,]+)', html, re.IGNORECASE)
        if not price_match:
            price_match = re.search(r'£([\d,]+)', html)
        price = int(price_match.group(1).replace(',', '')) if price_match else 0

        # Extract title/address
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        title = title_match.group(1).strip() if title_match else "Auction Property"

        postcode = extract_postcode(html) or ""
        units = extract_unit_count(html)
        tenure = extract_tenure(html)

        # Try to extract city from title/address
        city = ""
        if postcode:
            # First part of postcode often indicates city
            city = postcode.split()[0] if postcode else ""

        return {
            "title": title,
            "price": price,
            "address": title,
            "city": city,
            "postcode": postcode,
            "units": units.value,
            "tenure": tenure.value,
        }


async def fetch_onthemarket(url: str) -> dict:
    """Fetch property data from OnTheMarket URL."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not fetch OnTheMarket page")

        html = response.text

        price_match = re.search(r'£([\d,]+)', html)
        price = int(price_match.group(1).replace(',', '')) if price_match else 0

        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        title = title_match.group(1).strip() if title_match else "Property"

        postcode = extract_postcode(html) or ""
        units = extract_unit_count(html)
        tenure = extract_tenure(html)

        city = ""
        address_match = re.search(r'"streetAddress":"([^"]+)"', html)
        if address_match:
            parts = address_match.group(1).split(',')
            if len(parts) >= 2:
                city = parts[-1].strip()

        return {
            "title": title,
            "price": price,
            "address": title,
            "city": city,
            "postcode": postcode,
            "units": units.value,
            "tenure": tenure.value,
        }


async def fetch_generic(url: str) -> dict:
    """Generic property data extraction."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not fetch page")

        html = response.text

        # Generic price extraction
        price_match = re.search(r'£([\d,]+)', html)
        price = int(price_match.group(1).replace(',', '')) if price_match else 0

        # Generic title
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        title = title_match.group(1).strip() if title_match else "Property"

        postcode = extract_postcode(html) or ""
        units = extract_unit_count(html)
        tenure = extract_tenure(html)

        return {
            "title": title,
            "price": price,
            "address": "",
            "city": "",
            "postcode": postcode,
            "units": units.value,
            "tenure": tenure.value,
        }


class ValuationRequest(BaseModel):
    postcode: str
    asking_price: int
    num_units: int
    avg_bedrooms: int = 2


class ComparableSale(BaseModel):
    date: Optional[str] = None
    address: Optional[str] = None
    price: Optional[int] = None
    sqf: Optional[int] = None
    price_per_sqf: Optional[int] = None
    type: Optional[str] = None
    tenure: Optional[str] = None


class ValuationResponse(BaseModel):
    status: str
    asking_price: int
    num_units: int
    estimated_unit_value: Optional[int] = None
    unit_value_low: Optional[int] = None
    unit_value_high: Optional[int] = None
    unit_value_confidence: Optional[str] = None
    total_separated_value: Optional[int] = None
    gross_uplift: Optional[int] = None
    gross_uplift_percent: Optional[float] = None
    estimated_costs: Optional[int] = None
    net_uplift: Optional[int] = None
    net_per_unit: Optional[int] = None
    meets_threshold: Optional[bool] = None
    recommendation: Optional[str] = None
    message: Optional[str] = None
    # Land Registry / EPC data
    avg_price_per_sqf: Optional[int] = None
    comparable_sales: Optional[list[ComparableSale]] = None


@router.post("/valuation", response_model=ValuationResponse)
async def get_valuation(request: ValuationRequest):
    """
    Get PropertyData valuation for a title split opportunity.

    Uses PropertyData API to estimate individual unit values
    and calculate potential title split returns.
    """
    try:
        result = await calculate_title_split_potential(
            postcode=request.postcode,
            asking_price=request.asking_price,
            num_units=request.num_units,
            avg_bedrooms=request.avg_bedrooms,
        )
        return ValuationResponse(**result)

    except Exception as e:
        logger.error("Valuation failed", error=str(e), postcode=request.postcode)
        return ValuationResponse(
            status="error",
            asking_price=request.asking_price,
            num_units=request.num_units,
            message=str(e),
        )


class SoldPricesRequest(BaseModel):
    postcode: str
    property_type: str = "flat"


@router.post("/sold-prices")
async def get_sold_prices(request: SoldPricesRequest):
    """
    Get recent sold prices near a postcode.

    Returns comparable sales data for the area.
    """
    try:
        client = PropertyDataClient()
        sold_prices = await client.get_sold_prices(
            postcode=request.postcode,
            property_type=request.property_type,
        )
        return {
            "status": "success",
            "postcode": request.postcode,
            "sold_prices": sold_prices,
        }

    except Exception as e:
        logger.error("Sold prices lookup failed", error=str(e))
        return {
            "status": "error",
            "message": str(e),
            "sold_prices": [],
        }

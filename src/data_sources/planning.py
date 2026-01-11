import re
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()


# Planning portal URLs by council
PLANNING_PORTALS = {
    "liverpool": "https://planningandbuildingcontrol.liverpool.gov.uk/online-applications/",
    "manchester": "https://pa.manchester.gov.uk/online-applications/",
    "wigan": "https://planning.wigan.gov.uk/online-applications/",
    "leeds": "https://publicaccess.leeds.gov.uk/online-applications/",
    "sheffield": "https://planningapps.sheffield.gov.uk/online-applications/",
    "bradford": "https://planning.bradford.gov.uk/online-applications/",
    "newcastle": "https://publicaccess.newcastle.gov.uk/online-applications/",
    "bolton": "https://www.planningpa.bolton.gov.uk/online-applications/",
    "hull": "https://planningaccess.hullcc.gov.uk/online-applications/",
    "middlesbrough": "https://publicaccess.middlesbrough.gov.uk/online-applications/",
    "sunderland": "https://www.sunderland.gov.uk/online-applications/",
    "gateshead": "https://public.gateshead.gov.uk/online-applications/",
    "stockport": "https://planning.stockport.gov.uk/PlanningData/",
    "salford": "https://publicaccess.salford.gov.uk/publicaccess/",
    "oldham": "https://planningpa.oldham.gov.uk/online-applications/",
}

# Postcode prefix to council mapping (simplified)
POSTCODE_TO_COUNCIL = {
    "L": "liverpool",  # L1-L40
    "M": "manchester",  # M1-M90 (simplified - includes Salford, etc.)
    "WN": "wigan",
    "LS": "leeds",
    "S": "sheffield",  # S1-S99
    "BD": "bradford",
    "NE": "newcastle",
    "BL": "bolton",
    "HU": "hull",
    "TS": "middlesbrough",
    "SR": "sunderland",
    "SK": "stockport",
    "OL": "oldham",
}


@dataclass
class PlanningInfo:
    council: Optional[str]
    portal_url: Optional[str]
    search_url: Optional[str]
    inferred_use_class: Optional[str]
    has_article_4: bool
    hmo_check_required: bool
    planning_flags: list[str]


def postcode_to_council(postcode: str) -> Optional[str]:
    """Map a postcode to its local council."""
    postcode = postcode.upper().replace(" ", "")

    # Try 2-letter prefix first
    prefix_2 = postcode[:2]
    if prefix_2 in POSTCODE_TO_COUNCIL:
        return POSTCODE_TO_COUNCIL[prefix_2]

    # Try 1-letter prefix
    prefix_1 = postcode[:1]
    if prefix_1 in POSTCODE_TO_COUNCIL:
        return POSTCODE_TO_COUNCIL[prefix_1]

    return None


def get_planning_portal_url(postcode: str) -> Optional[str]:
    """
    Return the planning portal URL for manual lookup.

    For MVP, we generate a search URL - user clicks to investigate.
    Full automation would require per-council scraper development.
    """
    council = postcode_to_council(postcode)
    if not council:
        return None

    base_url = PLANNING_PORTALS.get(council)
    if base_url:
        # Format postcode for URL
        postcode_formatted = postcode.upper().replace(" ", "+")
        return f"{base_url}search.do?action=simple&searchType=Application&simpleSearchString={postcode_formatted}"

    return None


def infer_use_class_from_text(text: str) -> tuple[Optional[str], float]:
    """
    Infer the use class from listing description.

    Returns: (use_class, confidence)

    Use Classes:
    - C3: Dwelling houses (single household)
    - C4: Houses in multiple occupation (3-6 people)
    - Sui Generis: Large HMOs (7+ people), B&Bs, hostels
    """
    text_lower = text.lower()

    # Strong indicators
    if any(phrase in text_lower for phrase in ["hmo", "house in multiple occupation"]):
        if "licensed" in text_lower or "licence" in text_lower:
            return "C4", 0.85
        return "Sui Generis", 0.70

    if any(phrase in text_lower for phrase in ["bedsit", "bed-sit", "studio flat", "student let"]):
        return "C4", 0.60

    if any(phrase in text_lower for phrase in ["self contained", "self-contained"]):
        return "C3", 0.80

    if "block of flats" in text_lower or "residential block" in text_lower:
        return "C3", 0.75

    # Default assumption for flats
    return "C3", 0.50


def check_article_4_indicators(text: str) -> bool:
    """Check if listing mentions Article 4 restrictions."""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in [
        "article 4",
        "article four",
        "permitted development",
        "pd rights",
        "prior approval",
    ])


def check_hmo_indicators(text: str) -> tuple[bool, list[str]]:
    """Check if property may require HMO licensing."""
    text_lower = text.lower()
    indicators = []

    hmo_phrases = [
        ("hmo", "Explicit HMO mention"),
        ("house in multiple occupation", "Explicit HMO mention"),
        ("bedsit", "Bedsit configuration"),
        ("room let", "Room letting"),
        ("student accommodation", "Student accommodation"),
        ("multi-let", "Multi-let property"),
    ]

    for phrase, reason in hmo_phrases:
        if phrase in text_lower:
            indicators.append(reason)

    return len(indicators) > 0, indicators


def analyze_planning_context(postcode: str, description: str) -> PlanningInfo:
    """
    Analyze planning context for a property.

    Returns structured planning information for manual verification.
    """
    council = postcode_to_council(postcode)
    portal_url = PLANNING_PORTALS.get(council) if council else None
    search_url = get_planning_portal_url(postcode)

    use_class, _ = infer_use_class_from_text(description)
    has_article_4 = check_article_4_indicators(description)
    hmo_required, hmo_indicators = check_hmo_indicators(description)

    flags = []
    if has_article_4:
        flags.append("Article 4 direction may apply")
    if hmo_required:
        flags.extend(hmo_indicators)
    if use_class == "Sui Generis":
        flags.append("May require change of use permission")

    return PlanningInfo(
        council=council,
        portal_url=portal_url,
        search_url=search_url,
        inferred_use_class=use_class,
        has_article_4=has_article_4,
        hmo_check_required=hmo_required,
        planning_flags=flags,
    )


# Manual verification checklist
PLANNING_VERIFICATION_CHECKLIST = [
    {
        "item": "Current use class",
        "description": "Confirm the current lawful use class (C3/C4/Sui Generis)",
        "source": "Planning portal history or Lawful Development Certificate",
        "critical": True,
    },
    {
        "item": "Article 4 direction",
        "description": "Check if Article 4 removes permitted development rights",
        "source": "Council website / planning portal",
        "critical": True,
    },
    {
        "item": "HMO licensing",
        "description": "Check if HMO licence required/held",
        "source": "Council HMO register",
        "critical": True,
    },
    {
        "item": "Planning history",
        "description": "Review any previous applications/refusals",
        "source": "Planning portal search",
        "critical": False,
    },
    {
        "item": "Conservation area",
        "description": "Check if in conservation area (affects alterations)",
        "source": "Council interactive map",
        "critical": False,
    },
    {
        "item": "Listed building",
        "description": "Check if listed or adjacent to listed buildings",
        "source": "Historic England listing search",
        "critical": True,
    },
]

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Union, List


@dataclass
class ExtractionResult:
    value: Union[str, int, float, None]
    confidence: float
    pattern_matched: Optional[str] = None


@dataclass
class FloorAreaResult:
    sqft: Optional[float]
    sqm: Optional[float]
    confidence: float
    source: str  # 'explicit', 'calculated', 'typical'


# Word to number mapping
WORD_TO_NUMBER = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20,
}

# Typical floor areas by bedroom count (UK averages in sqft)
TYPICAL_FLOOR_AREAS_SQFT = {
    0: 350,   # Studio
    1: 450,   # 1-bed flat
    2: 650,   # 2-bed flat
    3: 850,   # 3-bed flat
    4: 1100,  # 4-bed flat
}


def normalize_numbers_in_text(text: str) -> str:
    """Replace word numbers with digits in text."""
    result = text.lower()
    for word, num in sorted(WORD_TO_NUMBER.items(), key=lambda x: -len(x[0])):
        result = re.sub(rf'\b{word}\b', str(num), result)
    return result


# Unit count extraction patterns (ordered by reliability)
UNIT_COUNT_PATTERNS = [
    # Explicit statements - high confidence
    (r'block of (\d+) (?:self[- ]?contained )?(?:flats?|apartments?|units?)', 0.95),
    (r'(\d+) (?:self[- ]?contained )?(?:flats?|apartments?|units?) (?:over|across|on)', 0.95),
    (r'currently (?:arranged|configured|set up) as (\d+) (?:flats?|units?|apartments?)', 0.95),
    (r'comprises? (?:of )?(\d+) (?:self[- ]?contained )?(?:flats?|units?|apartments?)', 0.95),
    (r'containing (\d+) (?:self[- ]?contained )?(?:flats?|units?|apartments?)', 0.93),
    (r'converted (?:into|to) (\d+)', 0.92),
    (r'(\d+) (?:self[- ]?contained )?(?:flats?|apartments?|units?)', 0.90),
    (r'(\d+) flats? in a? ?(?:converted|victorian|period|georgian|edwardian)', 0.92),
    # Floor-based patterns
    (r'ground floor flat (?:plus|and|with) (\d+) (?:flats?|units?) above', 0.90),
    (r'(\d+) floors? (?:of|with) (?:flats?|apartments?)', 0.85),
    # Bedroom-based inference
    (r'(\d+) ?x ?\d[- ]?bed(?:room)?', 0.85),  # "4 x 2-bed flats"
    (r'(\d+) \d[- ]?bedroom (?:flats?|apartments?|units?)', 0.85),
    # Counting patterns
    (r'(?:first|1st|ground) (?:and|&) (?:second|2nd) floor flats?', 0.80),  # Implies 2+ units
    (r'(\d+)[- ]?storey (?:building|block|house) (?:with|comprising)', 0.70),
    # Weaker patterns - lower confidence
    (r'(\d+)[- ]?storey', 0.50),  # May indicate units
]

# Tenure extraction patterns
TENURE_PATTERNS = {
    'freehold': [
        (r'\bfreehold\b(?! flat)', 0.95),  # "freehold" but not "freehold flat"
        (r'freehold block', 0.98),
        (r'all\s+(?:flats?\s+)?freehold', 0.95),
        (r'sold freehold', 0.90),
    ],
    'leasehold': [
        (r'\bleasehold\b', 0.95),
        (r'remaining (?:on )?lease', 0.90),
        (r'\d+ years? (?:remaining|left)', 0.85),
    ],
    'share_of_freehold': [
        (r'share of (?:the )?freehold', 0.98),
        (r'\bsof\b', 0.70),
    ],
}

# Refurbishment indicators
REFURB_INDICATORS = [
    ('needs modernisation', 0.9),
    ('refurbishment required', 0.95),
    ('refurbishment opportunity', 0.95),
    ('in need of updating', 0.85),
    ('requires updating', 0.85),
    ('renovation project', 0.90),
    ('development opportunity', 0.80),
    ('cash buyers only', 0.75),
    ('probate', 0.70),
    ('deceased estate', 0.70),
]

# Red flags (negative indicators)
RED_FLAGS = [
    ('flying freehold', 'title_complexity'),
    ('share of freehold', 'not_single_title'),
    ('commercial', 'mixed_use_complexity'),
    ('retail', 'mixed_use_complexity'),
    ('shop', 'mixed_use_complexity'),
    ('ground rent', 'leasehold_indicator'),
    ('service charge', 'leasehold_indicator'),
    ('management company', 'leasehold_indicator'),
    ('structural issues', 'condition_risk'),
    ('subsidence', 'condition_risk'),
    ('japanese knotweed', 'condition_risk'),
]


def extract_unit_count(text: str) -> ExtractionResult:
    """Extract unit count from listing text."""
    # Normalize word numbers to digits (e.g., "three flats" -> "3 flats")
    text_normalized = normalize_numbers_in_text(text)

    for pattern, confidence in UNIT_COUNT_PATTERNS:
        match = re.search(pattern, text_normalized)
        if match:
            try:
                count = int(match.group(1))
                if 2 <= count <= 50:  # Sanity check
                    return ExtractionResult(
                        value=count,
                        confidence=confidence,
                        pattern_matched=pattern
                    )
            except (ValueError, IndexError):
                continue

    return ExtractionResult(value=None, confidence=0.0)


def extract_tenure(text: str) -> ExtractionResult:
    """Extract tenure from listing text."""
    text_lower = text.lower()
    best_match = ExtractionResult(value='unknown', confidence=0.0)

    for tenure_type, patterns in TENURE_PATTERNS.items():
        for pattern, confidence in patterns:
            if re.search(pattern, text_lower):
                if confidence > best_match.confidence:
                    best_match = ExtractionResult(
                        value=tenure_type,
                        confidence=confidence,
                        pattern_matched=pattern
                    )

    return best_match


def extract_refurb_indicators(text: str) -> list[dict]:
    """Extract refurbishment indicators from listing text."""
    text_lower = text.lower()
    found = []

    for indicator, confidence in REFURB_INDICATORS:
        if indicator in text_lower:
            found.append({
                'indicator': indicator,
                'confidence': confidence
            })

    return found


def extract_red_flags(text: str) -> list[dict]:
    """Extract red flags from listing text."""
    text_lower = text.lower()
    found = []

    for phrase, flag_type in RED_FLAGS:
        if phrase in text_lower:
            found.append({
                'phrase': phrase,
                'flag_type': flag_type
            })

    return found


def extract_postcode(text: str) -> Optional[str]:
    """Extract UK postcode from text."""
    # UK postcode regex pattern
    pattern = r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b'
    match = re.search(pattern, text.upper())
    if match:
        postcode = match.group(1)
        # Normalize spacing
        if ' ' not in postcode:
            postcode = postcode[:-3] + ' ' + postcode[-3:]
        return postcode.upper()
    return None


def extract_bedrooms(text: str) -> list[dict]:
    """Extract bedroom breakdown from listing text."""
    text_lower = text.lower()
    breakdown = []

    # Pattern: "2 x 2-bed" or "3 x 1 bedroom"
    pattern = r'(\d+)\s*x\s*(\d+)[- ]?bed(?:room)?'
    matches = re.findall(pattern, text_lower)
    for count, beds in matches:
        breakdown.append({
            'count': int(count),
            'bedrooms': int(beds)
        })

    # Pattern: "2 x one bed, 2 x two bed"
    text_normalized = normalize_numbers_in_text(text_lower)
    pattern2 = r'(\d+)\s*x\s*(\d+)[- ]?bed(?:room)?'
    matches2 = re.findall(pattern2, text_normalized)
    for count, beds in matches2:
        if {'count': int(count), 'bedrooms': int(beds)} not in breakdown:
            breakdown.append({
                'count': int(count),
                'bedrooms': int(beds)
            })

    return breakdown


# Floor area extraction patterns
FLOOR_AREA_PATTERNS = [
    # Square feet patterns
    (r'(\d{2,4})\s*(?:sq\.?\s*ft\.?|sqft|square feet)', 'sqft', 0.95),
    (r'(\d{2,4})\s*ft²', 'sqft', 0.95),
    (r'approximately\s*(\d{2,4})\s*(?:sq\.?\s*ft\.?|sqft)', 'sqft', 0.85),
    (r'approx\.?\s*(\d{2,4})\s*(?:sq\.?\s*ft\.?|sqft)', 'sqft', 0.85),
    (r'circa\s*(\d{2,4})\s*(?:sq\.?\s*ft\.?|sqft)', 'sqft', 0.80),
    # Square meters patterns
    (r'(\d{2,4})\s*(?:sq\.?\s*m\.?|sqm|square met(?:er|re)s?)', 'sqm', 0.95),
    (r'(\d{2,4})\s*m²', 'sqm', 0.95),
    (r'approximately\s*(\d{2,4})\s*(?:sq\.?\s*m\.?|sqm)', 'sqm', 0.85),
]


def extract_floor_area(text: str, bedrooms: Optional[int] = None) -> FloorAreaResult:
    """
    Extract floor area from listing text.

    Returns both sqft and sqm (converting as needed).
    Falls back to typical area if bedrooms known.
    """
    text_lower = text.lower()

    for pattern, unit, confidence in FLOOR_AREA_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1))
                # Sanity check the value (realistic flat sizes)
                if unit == 'sqft' and 100 <= value <= 5000:
                    sqm = value / 10.764
                    return FloorAreaResult(
                        sqft=value,
                        sqm=round(sqm, 1),
                        confidence=confidence,
                        source='explicit'
                    )
                elif unit == 'sqm' and 10 <= value <= 500:
                    sqft = value * 10.764
                    return FloorAreaResult(
                        sqft=round(sqft, 0),
                        sqm=value,
                        confidence=confidence,
                        source='explicit'
                    )
            except (ValueError, IndexError):
                continue

    # Fall back to typical area based on bedrooms
    if bedrooms is not None and bedrooms in TYPICAL_FLOOR_AREAS_SQFT:
        typical_sqft = TYPICAL_FLOOR_AREAS_SQFT[bedrooms]
        return FloorAreaResult(
            sqft=typical_sqft,
            sqm=round(typical_sqft / 10.764, 1),
            confidence=0.50,
            source='typical'
        )

    return FloorAreaResult(sqft=None, sqm=None, confidence=0.0, source='unknown')


def extract_total_bedrooms(text: str) -> ExtractionResult:
    """
    Extract total bedroom count from listing text.

    This is different from extract_bedrooms which gets the breakdown.
    This extracts explicit statements like "6 bedroom property".
    """
    text_lower = text.lower()
    text_normalized = normalize_numbers_in_text(text_lower)

    # Explicit total bedroom patterns
    patterns = [
        (r'(\d+)\s*bed(?:room)?\s*(?:property|house|building|block)', 0.90),
        (r'(\d+)\s*bedroom', 0.85),
        (r'(\d+)\s*bed\b', 0.75),
    ]

    for pattern, confidence in patterns:
        match = re.search(pattern, text_normalized)
        if match:
            try:
                beds = int(match.group(1))
                if 1 <= beds <= 30:  # Sanity check
                    return ExtractionResult(
                        value=beds,
                        confidence=confidence,
                        pattern_matched=pattern
                    )
            except (ValueError, IndexError):
                continue

    return ExtractionResult(value=None, confidence=0.0)

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Union, List


@dataclass
class ExtractionResult:
    value: Union[str, int, None]
    confidence: float
    pattern_matched: Optional[str] = None


# Word to number mapping
WORD_TO_NUMBER = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20,
}


def normalize_numbers_in_text(text: str) -> str:
    """Replace word numbers with digits in text."""
    result = text.lower()
    for word, num in sorted(WORD_TO_NUMBER.items(), key=lambda x: -len(x[0])):
        result = re.sub(rf'\b{word}\b', str(num), result)
    return result


# Unit count extraction patterns (ordered by reliability)
UNIT_COUNT_PATTERNS = [
    # Explicit statements
    (r'block of (\d+) (?:self[- ]?contained )?(?:flats|apartments)', 0.95),
    (r'(\d+) (?:self[- ]?contained )?(?:flats|apartments|units)', 0.90),
    (r'(\d+) flats? in a? ?(?:converted|victorian|period)', 0.92),
    (r'comprises (\d+)', 0.85),
    (r'containing (\d+)', 0.85),
    (r'converted (?:into|to) (\d+)', 0.90),
    # Bedroom-based inference
    (r'(\d+) x \d[- ]?bed', 0.80),  # "4 x 2-bed flats"
    (r'(\d+) \d[- ]?bedroom flats', 0.80),
    # Weaker patterns
    (r'(\d+)[- ]?storey', 0.60),  # May indicate units
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

    return breakdown

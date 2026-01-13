import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import anthropic
import structlog

from src.config import get_settings

logger = structlog.get_logger()

FLOORPLAN_ANALYSIS_PROMPT = """You are analyzing a UK property floorplan image to extract room and layout information for a title splitting investment analysis.

**Task:**
Analyze this floorplan and identify:
1. Number of distinct residential units/flats visible
2. For each unit: count of bedrooms, bathrooms, reception rooms
3. Layout type classification (studio, 1-bed, 2-bed, etc.)
4. Any concerns about layout or self-containment

**Respond with JSON only (no markdown):**
{{
    "units_detected": <int>,
    "confidence": <float 0-1>,
    "units": [
        {{
            "unit_id": "<e.g., Ground Floor Flat, Flat 1>",
            "layout_type": "<studio|1-bed|2-bed|3-bed|4-bed+>",
            "bedrooms": <int>,
            "bathrooms": <int>,
            "reception_rooms": <int>,
            "has_kitchen": <bool>,
            "estimated_sqft": <int or null>,
            "notes": "<any observations about this unit>"
        }}
    ],
    "self_contained_assessment": {{
        "all_self_contained": <bool>,
        "concerns": ["<concern1>", "<concern2>"],
        "evidence": "<what indicates self-containment or lack thereof>"
    }},
    "layout_concerns": ["<concern1>", "<concern2>"],
    "suitable_for_title_split": <bool>,
    "analysis_notes": "<overall observations about the floorplan>"
}}"""


@dataclass
class UnitLayout:
    unit_id: str
    layout_type: str
    bedrooms: int
    bathrooms: int
    reception_rooms: int
    has_kitchen: bool
    estimated_sqft: Optional[int]
    notes: str


@dataclass
class SelfContainedAssessment:
    all_self_contained: bool
    concerns: list[str]
    evidence: str


@dataclass
class FloorplanAnalysis:
    units_detected: int
    confidence: float
    units: list[UnitLayout]
    self_contained_assessment: SelfContainedAssessment
    layout_concerns: list[str]
    suitable_for_title_split: bool
    analysis_notes: str
    raw_response: dict
    analyzed_at: datetime


class FloorplanAnalyzer:
    """Analyze floorplan images using Claude Vision."""

    def __init__(self):
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"

    async def analyze(
        self,
        image_base64: str,
        media_type: str,
    ) -> FloorplanAnalysis:
        """
        Analyze a floorplan image using Claude Vision.

        Args:
            image_base64: Base64-encoded image data
            media_type: MIME type (image/jpeg, image/png, image/webp, image/gif)

        Returns:
            FloorplanAnalysis with room counts and layout details
        """
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": FLOORPLAN_ANALYSIS_PROMPT,
                            },
                        ],
                    }
                ],
            )

            response_text = message.content[0].text
            # Clean up response - remove any markdown code blocks
            response_text = response_text.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            response_text = response_text.strip()

            data = json.loads(response_text)
            return self._parse_response(data)

        except json.JSONDecodeError as e:
            logger.error("Failed to parse floorplan analysis response", error=str(e))
            raise
        except anthropic.APIError as e:
            logger.error("Claude API error during floorplan analysis", error=str(e))
            raise

    def _parse_response(self, data: dict) -> FloorplanAnalysis:
        """Parse the AI response into structured dataclass."""
        units = []
        for unit_data in data.get("units", []):
            units.append(
                UnitLayout(
                    unit_id=unit_data.get("unit_id", "Unknown"),
                    layout_type=unit_data.get("layout_type", "unknown"),
                    bedrooms=unit_data.get("bedrooms", 0),
                    bathrooms=unit_data.get("bathrooms", 0),
                    reception_rooms=unit_data.get("reception_rooms", 0),
                    has_kitchen=unit_data.get("has_kitchen", False),
                    estimated_sqft=unit_data.get("estimated_sqft"),
                    notes=unit_data.get("notes", ""),
                )
            )

        self_contained = data.get("self_contained_assessment", {})

        return FloorplanAnalysis(
            units_detected=data.get("units_detected", 0),
            confidence=data.get("confidence", 0.0),
            units=units,
            self_contained_assessment=SelfContainedAssessment(
                all_self_contained=self_contained.get("all_self_contained", False),
                concerns=self_contained.get("concerns", []),
                evidence=self_contained.get("evidence", ""),
            ),
            layout_concerns=data.get("layout_concerns", []),
            suitable_for_title_split=data.get("suitable_for_title_split", False),
            analysis_notes=data.get("analysis_notes", ""),
            raw_response=data,
            analyzed_at=datetime.utcnow(),
        )

    def analysis_to_dict(self, analysis: FloorplanAnalysis) -> dict:
        """Convert FloorplanAnalysis to dictionary for JSON storage."""
        return {
            "units_detected": analysis.units_detected,
            "confidence": analysis.confidence,
            "units": [
                {
                    "unit_id": u.unit_id,
                    "layout_type": u.layout_type,
                    "bedrooms": u.bedrooms,
                    "bathrooms": u.bathrooms,
                    "reception_rooms": u.reception_rooms,
                    "has_kitchen": u.has_kitchen,
                    "estimated_sqft": u.estimated_sqft,
                    "notes": u.notes,
                }
                for u in analysis.units
            ],
            "self_contained_assessment": {
                "all_self_contained": analysis.self_contained_assessment.all_self_contained,
                "concerns": analysis.self_contained_assessment.concerns,
                "evidence": analysis.self_contained_assessment.evidence,
            },
            "layout_concerns": analysis.layout_concerns,
            "suitable_for_title_split": analysis.suitable_for_title_split,
            "analysis_notes": analysis.analysis_notes,
        }

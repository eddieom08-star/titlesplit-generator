import json
from dataclasses import dataclass
from typing import Optional

import anthropic
import structlog

from src.config import get_settings
from src.models.property import Property
from src.data_sources.epc import EPCRecord
from src.data_sources.land_registry import ComparableSale

logger = structlog.get_logger()

ANALYSIS_PROMPT = """You are analysing a UK property listing to determine if it's suitable for a title splitting investment strategy.

**Investment Criteria:**
- Freehold block of 2-10 self-contained flats on a SINGLE title
- Suitable for splitting into individual leasehold titles
- Ideally requires refurbishment (adds value before split)
- Northern England focus (Liverpool, Manchester, Leeds, etc.)

**Property Details:**
Title: {title}
Price: £{price:,}
Location: {address}, {postcode}

**Description:**
{description}

**Key Features:**
{features}

**EPC Data (if available):**
{epc_summary}

**Comparable Sales (if available):**
{comparables_summary}

**Analyse and respond with JSON only (no markdown):**
{{
    "unit_analysis": {{
        "estimated_units": <int>,
        "unit_confidence": <float 0-1>,
        "unit_breakdown": "<e.g., 2x 2-bed, 2x 1-bed>",
        "self_contained": <bool or null if unclear>,
        "self_contained_evidence": "<quote from listing>"
    }},
    "tenure_analysis": {{
        "likely_tenure": "<freehold|leasehold|share_of_freehold|unknown>",
        "tenure_confidence": <float 0-1>,
        "tenure_evidence": "<quote from listing>",
        "single_title_likely": <bool>,
        "single_title_evidence": "<reasoning>"
    }},
    "condition_analysis": {{
        "refurb_needed": <bool>,
        "refurb_scope": "<light|medium|heavy|unclear>",
        "condition_evidence": ["<quote1>", "<quote2>"],
        "epc_improvement_potential": <bool>
    }},
    "financial_analysis": {{
        "price_per_unit": <int>,
        "price_assessment": "<undervalued|fair|overvalued>",
        "comparable_individual_value": <int or null>,
        "estimated_gross_uplift_percent": <int or null>,
        "reasoning": "<explain valuation view>"
    }},
    "risk_analysis": {{
        "red_flags": ["<flag1>", "<flag2>"],
        "amber_flags": ["<flag1>"],
        "mitigation_notes": "<how risks could be addressed>"
    }},
    "title_split_viability": {{
        "viable": <bool>,
        "viability_score": <int 0-100>,
        "blockers": ["<blocker1>"],
        "enablers": ["<enabler1>"],
        "key_due_diligence": ["<item1>", "<item2>"]
    }},
    "recommendation": {{
        "action": "<proceed|review|decline>",
        "priority": "<high|medium|low>",
        "rationale": "<2-3 sentence summary>",
        "next_steps": ["<step1>", "<step2>"]
    }}
}}"""


@dataclass
class UnitAnalysis:
    estimated_units: int
    unit_confidence: float
    unit_breakdown: str
    self_contained: Optional[bool]
    self_contained_evidence: str


@dataclass
class TenureAnalysis:
    likely_tenure: str
    tenure_confidence: float
    tenure_evidence: str
    single_title_likely: bool
    single_title_evidence: str


@dataclass
class ConditionAnalysis:
    refurb_needed: bool
    refurb_scope: str
    condition_evidence: list[str]
    epc_improvement_potential: bool


@dataclass
class FinancialAnalysis:
    price_per_unit: int
    price_assessment: str
    comparable_individual_value: Optional[int]
    estimated_gross_uplift_percent: Optional[int]
    reasoning: str


@dataclass
class RiskAnalysis:
    red_flags: list[str]
    amber_flags: list[str]
    mitigation_notes: str


@dataclass
class ViabilityAnalysis:
    viable: bool
    viability_score: int
    blockers: list[str]
    enablers: list[str]
    key_due_diligence: list[str]


@dataclass
class Recommendation:
    action: str
    priority: str
    rationale: str
    next_steps: list[str]


@dataclass
class AIAnalysisResult:
    unit_analysis: UnitAnalysis
    tenure_analysis: TenureAnalysis
    condition_analysis: ConditionAnalysis
    financial_analysis: FinancialAnalysis
    risk_analysis: RiskAnalysis
    title_split_viability: ViabilityAnalysis
    recommendation: Recommendation
    raw_response: dict


class AnalysisEngine:
    """AI-powered property analysis engine using Claude."""

    def __init__(self):
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"

    async def analyze_property(
        self,
        property: Property,
        description: str,
        epcs: Optional[list[EPCRecord]] = None,
        comparables: Optional[list[ComparableSale]] = None,
    ) -> AIAnalysisResult:
        """Run AI analysis on a property."""
        # Build EPC summary
        epc_summary = "No EPC data available"
        if epcs:
            epc_lines = []
            for epc in epcs:
                epc_lines.append(
                    f"- {epc.address}: Rating {epc.current_rating}, "
                    f"{epc.floor_area}sqm, {epc.property_type}"
                )
            epc_summary = "\n".join(epc_lines)

        # Build comparables summary
        comparables_summary = "No comparable sales data available"
        if comparables:
            comp_lines = []
            for comp in comparables:
                comp_lines.append(
                    f"- {comp.address}: £{comp.price:,} "
                    f"({comp.sale_date.strftime('%b %Y')})"
                )
            comparables_summary = "\n".join(comp_lines)

        # Format the prompt
        prompt = ANALYSIS_PROMPT.format(
            title=property.title,
            price=property.asking_price,
            address=property.address_line1,
            postcode=property.postcode,
            description=description,
            features="See description",
            epc_summary=epc_summary,
            comparables_summary=comparables_summary,
        )

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
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
            logger.error("Failed to parse AI response", error=str(e))
            raise
        except anthropic.APIError as e:
            logger.error("Claude API error", error=str(e))
            raise

    def _parse_response(self, data: dict) -> AIAnalysisResult:
        """Parse the AI response into structured dataclasses."""
        unit = data.get("unit_analysis", {})
        tenure = data.get("tenure_analysis", {})
        condition = data.get("condition_analysis", {})
        financial = data.get("financial_analysis", {})
        risk = data.get("risk_analysis", {})
        viability = data.get("title_split_viability", {})
        rec = data.get("recommendation", {})

        return AIAnalysisResult(
            unit_analysis=UnitAnalysis(
                estimated_units=unit.get("estimated_units", 0),
                unit_confidence=unit.get("unit_confidence", 0.0),
                unit_breakdown=unit.get("unit_breakdown", ""),
                self_contained=unit.get("self_contained"),
                self_contained_evidence=unit.get("self_contained_evidence", ""),
            ),
            tenure_analysis=TenureAnalysis(
                likely_tenure=tenure.get("likely_tenure", "unknown"),
                tenure_confidence=tenure.get("tenure_confidence", 0.0),
                tenure_evidence=tenure.get("tenure_evidence", ""),
                single_title_likely=tenure.get("single_title_likely", False),
                single_title_evidence=tenure.get("single_title_evidence", ""),
            ),
            condition_analysis=ConditionAnalysis(
                refurb_needed=condition.get("refurb_needed", False),
                refurb_scope=condition.get("refurb_scope", "unclear"),
                condition_evidence=condition.get("condition_evidence", []),
                epc_improvement_potential=condition.get("epc_improvement_potential", False),
            ),
            financial_analysis=FinancialAnalysis(
                price_per_unit=financial.get("price_per_unit", 0),
                price_assessment=financial.get("price_assessment", "unknown"),
                comparable_individual_value=financial.get("comparable_individual_value"),
                estimated_gross_uplift_percent=financial.get("estimated_gross_uplift_percent"),
                reasoning=financial.get("reasoning", ""),
            ),
            risk_analysis=RiskAnalysis(
                red_flags=risk.get("red_flags", []),
                amber_flags=risk.get("amber_flags", []),
                mitigation_notes=risk.get("mitigation_notes", ""),
            ),
            title_split_viability=ViabilityAnalysis(
                viable=viability.get("viable", False),
                viability_score=viability.get("viability_score", 0),
                blockers=viability.get("blockers", []),
                enablers=viability.get("enablers", []),
                key_due_diligence=viability.get("key_due_diligence", []),
            ),
            recommendation=Recommendation(
                action=rec.get("action", "review"),
                priority=rec.get("priority", "low"),
                rationale=rec.get("rationale", ""),
                next_steps=rec.get("next_steps", []),
            ),
            raw_response=data,
        )

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

ANALYSIS_PROMPT = """You are a senior property investment analyst specialising in UK title splitting strategies.

## CRITICAL INSTRUCTION
**READ THE ENTIRE PROPERTY DESCRIPTION CAREFULLY BEFORE ANALYSIS.**
Do NOT skim. Extract EVERY relevant detail. Missing information leads to bad investment decisions.

---

## PROPERTY DATA

**Listing:**
- Title: {title}
- Price: £{price:,}
- Location: {address}, {postcode}

**Full Description (READ COMPLETELY):**
{description}

**Key Features:**
{features}

**EPC Data:**
{epc_summary}

**Comparable Sales:**
{comparables_summary}

---

## INVESTMENT CRITERIA
- Freehold block of 2-10 self-contained flats on SINGLE title
- Suitable for splitting into individual leasehold titles
- Ideally requires refurbishment (adds value before split)
- Northern England focus (Liverpool, Manchester, Leeds, etc.)

---

## ANALYSIS FRAMEWORK (Role Stacking)

Analyse this property from FOUR expert perspectives:

### 1. INVESTOR LENS
- Is this a good deal? What's the realistic profit potential?
- What's the exit strategy? Individual sales vs. refinance & hold?
- How does this compare to other opportunities?

### 2. SURVEYOR LENS
- What condition issues are evident or implied?
- What's likely hidden? (e.g., "in need of modernisation" = significant work)
- What structural/damp/access concerns should be investigated?

### 3. LENDER LENS
- Would a bridge lender fund this at 70-75% LTV?
- What would concern an underwriter?
- Is the GDV realistic and defensible?

### 4. SOLICITOR LENS
- What title/legal issues might arise?
- Is this actually splittable? (access, services, planning)
- What conveyancing complications are likely?

---

## VERIFICATION (Self-Critique)

Before finalising, check your analysis:
- Did you read the FULL description?
- Did you quote specific evidence from the listing?
- Are your estimates conservative or optimistic?
- What did you assume that isn't explicitly stated?
- What's the WORST case scenario?

---

## RESPONSE FORMAT (JSON only, no markdown):

{{
    "description_review": {{
        "word_count_read": <int - approximate words in description>,
        "key_phrases_extracted": ["<important phrase 1>", "<phrase 2>", "<phrase 3>"],
        "missing_information": ["<what's NOT mentioned that should be>"],
        "red_flag_phrases": ["<concerning language>"]
    }},
    "unit_analysis": {{
        "estimated_units": <int>,
        "unit_confidence": <float 0-1>,
        "unit_breakdown": "<e.g., 2x 2-bed, 2x 1-bed>",
        "self_contained": <bool or null if unclear>,
        "self_contained_evidence": "<direct quote from listing>",
        "access_arrangement": "<shared entrance, separate, unclear>"
    }},
    "tenure_analysis": {{
        "likely_tenure": "<freehold|leasehold|share_of_freehold|unknown>",
        "tenure_confidence": <float 0-1>,
        "tenure_evidence": "<direct quote from listing>",
        "single_title_likely": <bool>,
        "single_title_evidence": "<reasoning with quotes>"
    }},
    "condition_analysis": {{
        "refurb_needed": <bool>,
        "refurb_scope": "<cosmetic|light|medium|heavy|full_gut>",
        "estimated_refurb_cost_per_unit": <int>,
        "condition_evidence": ["<quote1>", "<quote2>"],
        "hidden_issues_likely": ["<issue1>", "<issue2>"],
        "epc_improvement_potential": <bool>
    }},
    "expert_perspectives": {{
        "investor_view": {{
            "verdict": "<strong_buy|buy|hold|avoid>",
            "profit_potential": "<high|medium|low|negative>",
            "reasoning": "<2 sentences>"
        }},
        "surveyor_view": {{
            "condition_grade": "<A|B|C|D|F>",
            "main_concerns": ["<concern1>", "<concern2>"],
            "recommended_surveys": ["<survey1>", "<survey2>"]
        }},
        "lender_view": {{
            "fundable": <bool>,
            "likely_ltv": <int 0-75>,
            "underwriter_concerns": ["<concern1>"]
        }},
        "solicitor_view": {{
            "splittable": "<yes|likely|uncertain|unlikely|no>",
            "legal_risks": ["<risk1>", "<risk2>"],
            "title_complexity": "<simple|moderate|complex>"
        }}
    }},
    "financial_analysis": {{
        "price_per_unit": <int>,
        "price_assessment": "<significantly_undervalued|undervalued|fair|overvalued|significantly_overvalued>",
        "comparable_individual_value": <int or null>,
        "estimated_gross_uplift_percent": <int or null>,
        "estimated_net_profit": <int or null>,
        "reasoning": "<detailed explanation with numbers>"
    }},
    "risk_analysis": {{
        "red_flags": ["<critical issue>"],
        "amber_flags": ["<caution item>"],
        "green_flags": ["<positive indicator>"],
        "worst_case_scenario": "<what could go wrong>",
        "mitigation_notes": "<how to address risks>"
    }},
    "title_split_viability": {{
        "viable": <bool>,
        "viability_score": <int 0-100>,
        "blockers": ["<blocker1>"],
        "enablers": ["<enabler1>"],
        "key_due_diligence": ["<specific action item>"]
    }},
    "verification_notes": {{
        "assumptions_made": ["<assumption1>", "<assumption2>"],
        "confidence_level": "<high|medium|low>",
        "information_gaps": ["<what we don't know>"],
        "analysis_caveats": "<important limitations>"
    }},
    "recommendation": {{
        "action": "<proceed|review|decline>",
        "priority": "<high|medium|low>",
        "rationale": "<3-4 sentence summary covering all perspectives>",
        "next_steps": ["<specific action 1>", "<specific action 2>", "<specific action 3>"],
        "dealbreaker_questions": ["<question that must be answered before proceeding>"]
    }}
}}"""


@dataclass
class DescriptionReview:
    word_count_read: int
    key_phrases_extracted: list[str]
    missing_information: list[str]
    red_flag_phrases: list[str]


@dataclass
class UnitAnalysis:
    estimated_units: int
    unit_confidence: float
    unit_breakdown: str
    self_contained: Optional[bool]
    self_contained_evidence: str
    access_arrangement: str = "unclear"


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
    estimated_refurb_cost_per_unit: int = 0
    hidden_issues_likely: list[str] = None

    def __post_init__(self):
        if self.hidden_issues_likely is None:
            self.hidden_issues_likely = []


@dataclass
class ExpertPerspectives:
    investor_view: dict
    surveyor_view: dict
    lender_view: dict
    solicitor_view: dict


@dataclass
class FinancialAnalysis:
    price_per_unit: int
    price_assessment: str
    comparable_individual_value: Optional[int]
    estimated_gross_uplift_percent: Optional[int]
    estimated_net_profit: Optional[int]
    reasoning: str


@dataclass
class RiskAnalysis:
    red_flags: list[str]
    amber_flags: list[str]
    green_flags: list[str]
    worst_case_scenario: str
    mitigation_notes: str


@dataclass
class ViabilityAnalysis:
    viable: bool
    viability_score: int
    blockers: list[str]
    enablers: list[str]
    key_due_diligence: list[str]


@dataclass
class VerificationNotes:
    assumptions_made: list[str]
    confidence_level: str
    information_gaps: list[str]
    analysis_caveats: str


@dataclass
class Recommendation:
    action: str
    priority: str
    rationale: str
    next_steps: list[str]
    dealbreaker_questions: list[str] = None

    def __post_init__(self):
        if self.dealbreaker_questions is None:
            self.dealbreaker_questions = []


@dataclass
class AIAnalysisResult:
    description_review: DescriptionReview
    unit_analysis: UnitAnalysis
    tenure_analysis: TenureAnalysis
    condition_analysis: ConditionAnalysis
    expert_perspectives: ExpertPerspectives
    financial_analysis: FinancialAnalysis
    risk_analysis: RiskAnalysis
    title_split_viability: ViabilityAnalysis
    verification_notes: VerificationNotes
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
                max_tokens=4000,  # Increased for comprehensive analysis
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
        desc_review = data.get("description_review", {})
        unit = data.get("unit_analysis", {})
        tenure = data.get("tenure_analysis", {})
        condition = data.get("condition_analysis", {})
        experts = data.get("expert_perspectives", {})
        financial = data.get("financial_analysis", {})
        risk = data.get("risk_analysis", {})
        viability = data.get("title_split_viability", {})
        verification = data.get("verification_notes", {})
        rec = data.get("recommendation", {})

        return AIAnalysisResult(
            description_review=DescriptionReview(
                word_count_read=desc_review.get("word_count_read", 0),
                key_phrases_extracted=desc_review.get("key_phrases_extracted", []),
                missing_information=desc_review.get("missing_information", []),
                red_flag_phrases=desc_review.get("red_flag_phrases", []),
            ),
            unit_analysis=UnitAnalysis(
                estimated_units=unit.get("estimated_units", 0),
                unit_confidence=unit.get("unit_confidence", 0.0),
                unit_breakdown=unit.get("unit_breakdown", ""),
                self_contained=unit.get("self_contained"),
                self_contained_evidence=unit.get("self_contained_evidence", ""),
                access_arrangement=unit.get("access_arrangement", "unclear"),
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
                estimated_refurb_cost_per_unit=condition.get("estimated_refurb_cost_per_unit", 0),
                hidden_issues_likely=condition.get("hidden_issues_likely", []),
            ),
            expert_perspectives=ExpertPerspectives(
                investor_view=experts.get("investor_view", {}),
                surveyor_view=experts.get("surveyor_view", {}),
                lender_view=experts.get("lender_view", {}),
                solicitor_view=experts.get("solicitor_view", {}),
            ),
            financial_analysis=FinancialAnalysis(
                price_per_unit=financial.get("price_per_unit", 0),
                price_assessment=financial.get("price_assessment", "unknown"),
                comparable_individual_value=financial.get("comparable_individual_value"),
                estimated_gross_uplift_percent=financial.get("estimated_gross_uplift_percent"),
                estimated_net_profit=financial.get("estimated_net_profit"),
                reasoning=financial.get("reasoning", ""),
            ),
            risk_analysis=RiskAnalysis(
                red_flags=risk.get("red_flags", []),
                amber_flags=risk.get("amber_flags", []),
                green_flags=risk.get("green_flags", []),
                worst_case_scenario=risk.get("worst_case_scenario", ""),
                mitigation_notes=risk.get("mitigation_notes", ""),
            ),
            title_split_viability=ViabilityAnalysis(
                viable=viability.get("viable", False),
                viability_score=viability.get("viability_score", 0),
                blockers=viability.get("blockers", []),
                enablers=viability.get("enablers", []),
                key_due_diligence=viability.get("key_due_diligence", []),
            ),
            verification_notes=VerificationNotes(
                assumptions_made=verification.get("assumptions_made", []),
                confidence_level=verification.get("confidence_level", "low"),
                information_gaps=verification.get("information_gaps", []),
                analysis_caveats=verification.get("analysis_caveats", ""),
            ),
            recommendation=Recommendation(
                action=rec.get("action", "review"),
                priority=rec.get("priority", "low"),
                rationale=rec.get("rationale", ""),
                next_steps=rec.get("next_steps", []),
                dealbreaker_questions=rec.get("dealbreaker_questions", []),
            ),
            raw_response=data,
        )

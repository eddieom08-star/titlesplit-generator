from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UnitDetail(BaseModel):
    """Individual unit information."""
    unit_identifier: str
    beds: Optional[int] = None
    floor_area_sqft: Optional[float] = None
    epc_rating: Optional[str] = None
    epc_potential: Optional[str] = None
    estimated_value: Optional[int] = None
    value_confidence: str = "low"


class CostBreakdown(BaseModel):
    """Detailed cost breakdown per Framework Section 5."""
    solicitor_fees: int
    land_registry_fees: int
    title_plan_costs: int
    lender_consent_fee: int
    lender_legal_costs: int
    valuation_fees: int
    insurance_costs: int
    contingency: int
    total: int
    per_unit: int


class BenefitAnalysis(BaseModel):
    """Benefit analysis per Framework Section 5."""
    current_value: int
    aggregate_individual_value: int
    gross_uplift: int
    gross_uplift_percent: float
    transaction_costs: int
    net_uplift: int
    net_uplift_percent: float
    net_benefit_per_unit: int
    meets_threshold: bool  # >£2k per unit
    cost_ratio_acceptable: bool  # <3% of value


class RiskItem(BaseModel):
    """Individual risk assessment item."""
    level: str  # low, medium, high
    description: str
    mitigation: Optional[str] = None


class RiskAssessment(BaseModel):
    """Risk matrix per Framework Section 6."""
    overall_risk: str  # low, medium, high
    title_risk: RiskItem
    lender_consent_risk: RiskItem
    boundary_risk: RiskItem
    condition_risk: RiskItem
    market_risk: RiskItem
    red_flags: list[str] = Field(default_factory=list)
    amber_flags: list[str] = Field(default_factory=list)
    mitigation_strategies: list[str] = Field(default_factory=list)


class DueDiligenceItem(BaseModel):
    """Checklist item for due diligence."""
    item: str
    category: str  # title, legal, physical, financial
    status: str = "pending"  # pending, verified, issue_found
    notes: Optional[str] = None
    action_required: Optional[str] = None


class FullAnalysis(BaseModel):
    """Full analysis results."""
    unit_analysis: dict
    tenure_analysis: dict
    condition_analysis: dict
    financial_analysis: dict
    viability_analysis: dict


class ComparableResponse(BaseModel):
    """Comparable sale response."""
    address: str
    postcode: str
    price: int
    sale_date: datetime
    beds: Optional[int] = None
    floor_area_sqft: Optional[float] = None
    distance_meters: Optional[int] = None


class OpportunityCard(BaseModel):
    """Summary card for deal feed."""
    id: UUID
    source_url: str
    title: str
    price: int
    city: str
    postcode: str

    # Key metrics
    estimated_units: int
    price_per_unit: int
    opportunity_score: int

    # Quick indicators
    tenure: str
    tenure_confidence: float
    avg_epc: Optional[str] = None
    refurb_needed: bool = False

    # Financial summary
    estimated_gross_uplift_percent: Optional[int] = None
    estimated_net_benefit_per_unit: Optional[int] = None

    # Status
    recommendation: str = "review"  # proceed, review, decline
    priority: str = "medium"  # high, medium, low

    # Meta
    first_seen: datetime
    images: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class OpportunityDetail(OpportunityCard):
    """Full opportunity details."""

    # Extended property info
    description: str = ""
    key_features: list[str] = Field(default_factory=list)
    agent_name: Optional[str] = None
    agent_phone: Optional[str] = None

    # Unit breakdown
    units: list[UnitDetail] = Field(default_factory=list)

    # Full analysis
    analysis: Optional[FullAnalysis] = None

    # Costs and benefits
    estimated_costs: Optional[CostBreakdown] = None
    estimated_benefits: Optional[BenefitAnalysis] = None

    # Risk assessment
    risks: Optional[RiskAssessment] = None

    # Due diligence checklist
    due_diligence: list[DueDiligenceItem] = Field(default_factory=list)

    # External links
    planning_portal_url: Optional[str] = None
    land_registry_search_url: Optional[str] = None

    # Comparables used
    comparables: list[ComparableResponse] = Field(default_factory=list)


# Strategy Memorandum components
class ExecutiveSummary(BaseModel):
    """Executive summary for strategy memorandum."""
    property_address: str
    recommendation: str
    key_metrics: dict
    summary_rationale: str


class CurrentStructureAnalysis(BaseModel):
    """Current structure analysis."""
    tenure: str
    title_details: dict
    unit_schedule: list[dict]
    current_valuation: int


class ProposedStructure(BaseModel):
    """Proposed split structure."""
    new_titles: list[dict]
    lease_terms: dict
    service_charge_structure: dict


class FinancialAnalysisDetail(BaseModel):
    """Detailed financial analysis."""
    costs: CostBreakdown
    benefits: BenefitAnalysis
    sensitivity_analysis: dict
    break_even_analysis: dict


class ImplementationPlan(BaseModel):
    """Implementation plan."""
    phases: list[dict]
    timeline_weeks: int
    key_milestones: list[dict]
    dependencies: list[str]


class RiskAssessmentDetail(BaseModel):
    """Detailed risk assessment."""
    risk_matrix: list[RiskItem]
    mitigation_plan: list[dict]
    residual_risks: list[str]


class Appendices(BaseModel):
    """Report appendices."""
    comparable_evidence: list[dict]
    epc_data: list[dict]
    planning_notes: Optional[str] = None
    title_notes: Optional[str] = None


class StrategyMemorandum(BaseModel):
    """
    Full strategy memorandum output per Framework Section 9.
    """
    generated_at: datetime
    property_id: UUID
    executive_summary: ExecutiveSummary
    current_structure: CurrentStructureAnalysis
    proposed_structure: ProposedStructure
    financial_analysis: FinancialAnalysisDetail
    implementation_plan: ImplementationPlan
    risk_assessment: RiskAssessmentDetail
    appendices: Appendices

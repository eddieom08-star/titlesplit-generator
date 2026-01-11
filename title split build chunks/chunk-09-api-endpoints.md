## CHUNK 9: API Endpoints & Frontend Data Contracts

### 9.1 Core API Endpoints

```python
# src/api/opportunities.py

@router.get("/opportunities", response_model=list[OpportunityCard])
async def list_opportunities(
    min_score: int = 60,
    max_price: int = None,
    min_units: int = 2,
    max_units: int = 10,
    cities: list[str] = None,
    sort_by: str = "score",  # score, price, date, uplift
    limit: int = 50,
):
    """
    List title split opportunities.
    
    Returns summary cards for the deal feed.
    """
    pass


@router.get("/opportunities/{id}", response_model=OpportunityDetail)
async def get_opportunity(id: UUID):
    """
    Get full opportunity details.
    
    Includes all analysis, costs, benefits, and recommended actions.
    """
    pass


@router.get("/opportunities/{id}/report", response_model=StrategyMemorandum)
async def generate_report(id: UUID):
    """
    Generate a Strategy Memorandum per Framework Section 9.
    
    Returns structured report matching framework output format.
    """
    pass
```

### 9.2 Response Models

```python
# src/models/responses.py

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
    avg_epc: str
    refurb_needed: bool
    
    # Financial summary
    estimated_gross_uplift_percent: Optional[int]
    estimated_net_benefit_per_unit: Optional[int]
    
    # Status
    recommendation: str  # proceed, review, decline
    priority: str  # high, medium, low
    
    # Meta
    first_seen: datetime
    images: list[str]


class OpportunityDetail(OpportunityCard):
    """Full opportunity details."""
    
    # Extended property info
    description: str
    key_features: list[str]
    agent_name: str
    agent_phone: str
    
    # Unit breakdown
    units: list[UnitDetail]
    
    # Full analysis
    analysis: FullAnalysis
    
    # Costs and benefits
    estimated_costs: CostBreakdown
    estimated_benefits: BenefitAnalysis
    
    # Risk assessment
    risks: RiskAssessment
    
    # Due diligence checklist
    due_diligence: list[DueDiligenceItem]
    
    # External links
    planning_portal_url: Optional[str]
    land_registry_search_url: str
    
    # Comparables used
    comparables: list[Comparable]


class UnitDetail(BaseModel):
    """Individual unit information."""
    unit_identifier: str
    beds: Optional[int]
    floor_area_sqft: Optional[float]
    epc_rating: Optional[str]
    epc_potential: Optional[str]
    estimated_value: Optional[int]
    value_confidence: str


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


class RiskAssessment(BaseModel):
    """Risk matrix per Framework Section 6."""
    overall_risk: str  # low, medium, high
    
    # Individual risks
    title_risk: RiskItem
    lender_consent_risk: RiskItem
    boundary_risk: RiskItem
    condition_risk: RiskItem
    market_risk: RiskItem
    
    # Red and amber flags
    red_flags: list[str]
    amber_flags: list[str]
    mitigation_strategies: list[str]


class DueDiligenceItem(BaseModel):
    """Checklist item for due diligence."""
    item: str
    category: str  # title, legal, physical, financial
    status: str  # pending, verified, issue_found
    notes: Optional[str]
    action_required: Optional[str]


class StrategyMemorandum(BaseModel):
    """
    Full strategy memorandum output per Framework Section 9.
    
    Structure:
    1. Executive Summary
    2. Current Structure Analysis
    3. Proposed Structure
    4. Financial Analysis
    5. Implementation Plan
    6. Risk Assessment
    7. Appendices
    """
    executive_summary: ExecutiveSummary
    current_structure: CurrentStructureAnalysis
    proposed_structure: ProposedStructure
    financial_analysis: FinancialAnalysisDetail
    implementation_plan: ImplementationPlan
    risk_assessment: RiskAssessmentDetail
    appendices: Appendices
```

---


## CHUNK 14: Manual Input Schema & Validation

### 14.1 Manual Input Categories

```python
# src/models/manual_inputs.py

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import date


class VerificationStatus(str, Enum):
    NOT_CHECKED = "not_checked"
    VERIFIED_OK = "verified_ok"
    VERIFIED_ISSUE = "verified_issue"
    VERIFIED_BLOCKER = "verified_blocker"
    NOT_APPLICABLE = "not_applicable"


# ============================================================================
# TITLE & TENURE INPUTS
# ============================================================================

class TitleVerification(BaseModel):
    """Manual input: Land Registry title verification."""
    
    # Basic title info
    title_number: Optional[str] = Field(
        None,
        description="HM Land Registry title number (e.g., MS123456)"
    )
    title_class: Optional[str] = Field(
        None,
        description="Title class: absolute, qualified, possessory"
    )
    
    # Tenure confirmation
    tenure_confirmed: Optional[str] = Field(
        None,
        description="Confirmed tenure: freehold, leasehold"
    )
    is_single_title: Optional[bool] = Field(
        None,
        description="Confirm all units on single title"
    )
    
    # Registered proprietor
    proprietor_name: Optional[str] = None
    proprietor_type: Optional[str] = Field(
        None,
        description="individual, company, trust, other"
    )
    
    verification_date: Optional[date] = None
    verified_by: Optional[str] = None
    notes: Optional[str] = None


class ExistingCharge(BaseModel):
    """Individual charge/mortgage on the title."""
    
    charge_date: Optional[date] = None
    lender_name: str
    charge_type: str = Field(
        ...,
        description="legal_charge, equitable_charge, charging_order, restriction"
    )
    
    # Amount (if known)
    original_amount: Optional[int] = None
    estimated_current_balance: Optional[int] = None
    
    # Critical flags
    is_all_monies_charge: Optional[bool] = Field(
        None,
        description="All-monies charge affects release mechanics"
    )
    has_consent_restriction: Optional[bool] = Field(
        None,
        description="Restriction requiring lender consent for disposals"
    )
    
    # Lender attitude (if known)
    lender_contacted: bool = False
    consent_likelihood: Optional[str] = Field(
        None,
        description="likely, uncertain, unlikely, refused"
    )
    consent_fee_quoted: Optional[int] = None
    
    notes: Optional[str] = None


class RestrictiveCovenant(BaseModel):
    """Restrictive covenant affecting the land."""
    
    covenant_summary: str = Field(
        ...,
        description="Brief description of the covenant"
    )
    covenant_type: str = Field(
        ...,
        description="use_restriction, building_restriction, alienation, other"
    )
    
    # Key questions
    affects_title_split: Optional[bool] = Field(
        None,
        description="Does this covenant prevent or complicate splitting?"
    )
    breach_risk: Optional[str] = Field(
        None,
        description="none, low, medium, high"
    )
    
    # Resolution
    can_be_released: Optional[bool] = None
    insurance_available: Optional[bool] = None
    insurance_cost_estimate: Optional[int] = None
    
    notes: Optional[str] = None


class Easement(BaseModel):
    """Easement (right of way, services, etc.)."""
    
    easement_type: str = Field(
        ...,
        description="right_of_way, drainage, utilities, light, support, other"
    )
    benefits_or_burdens: str = Field(
        ...,
        description="benefit (we have the right) or burden (others have right over us)"
    )
    
    description: str
    
    # Impact assessment
    affects_title_split: Optional[bool] = None
    requires_new_easements: Optional[bool] = Field(
        None,
        description="Will split require creating new easements?"
    )
    
    notes: Optional[str] = None


class TitleInputs(BaseModel):
    """All title-related manual inputs."""
    
    verification: Optional[TitleVerification] = None
    charges: List[ExistingCharge] = []
    covenants: List[RestrictiveCovenant] = []
    easements: List[Easement] = []
    
    # Overall title assessment
    title_defects_found: List[str] = []
    title_insurance_required: bool = False
    title_insurance_cost: Optional[int] = None


# ============================================================================
# PLANNING & LICENSING INPUTS
# ============================================================================

class PlanningStatus(BaseModel):
    """Manual input: Planning verification."""
    
    # Current use
    current_use_class: Optional[str] = Field(
        None,
        description="C3 (dwelling), C4 (small HMO), sui generis, mixed"
    )
    use_class_verified: bool = False
    
    # Planning history
    has_planning_history: Optional[bool] = None
    relevant_applications: List[str] = []  # Application references
    
    # Key planning issues
    in_article_4_area: Optional[bool] = Field(
        None,
        description="Article 4 direction restricting permitted development"
    )
    in_conservation_area: Optional[bool] = None
    is_listed_building: Optional[bool] = None
    
    # Conversion compliance
    original_conversion_consented: Optional[bool] = Field(
        None,
        description="Was original conversion to flats properly consented?"
    )
    building_regs_signed_off: Optional[bool] = None
    
    # Outstanding issues
    enforcement_notices: List[str] = []
    planning_conditions_outstanding: List[str] = []
    
    notes: Optional[str] = None


class HMOLicensing(BaseModel):
    """Manual input: HMO licensing status."""
    
    # Applicability
    requires_mandatory_licence: Optional[bool] = Field(
        None,
        description="5+ occupants, 2+ households = mandatory"
    )
    requires_additional_licence: Optional[bool] = Field(
        None,
        description="Check if council has additional licensing scheme"
    )
    requires_selective_licence: Optional[bool] = Field(
        None,
        description="Check if area has selective licensing"
    )
    
    # Current status
    licence_held: Optional[bool] = None
    licence_number: Optional[str] = None
    licence_expiry: Optional[date] = None
    licence_holder: Optional[str] = None
    
    # Transferability
    licence_transferable: Optional[bool] = Field(
        None,
        description="Can licence transfer to new owner?"
    )
    
    # Compliance
    meets_hmo_standards: Optional[bool] = None
    fire_safety_compliant: Optional[bool] = None
    room_sizes_compliant: Optional[bool] = None
    
    # Issues
    licence_conditions: List[str] = []
    compliance_issues: List[str] = []
    
    notes: Optional[str] = None


class PlanningInputs(BaseModel):
    """All planning-related manual inputs."""
    
    planning_status: Optional[PlanningStatus] = None
    hmo_licensing: Optional[HMOLicensing] = None
    
    # Council contact
    council_name: Optional[str] = None
    planning_officer_contacted: bool = False
    licensing_officer_contacted: bool = False


# ============================================================================
# PHYSICAL VERIFICATION INPUTS
# ============================================================================

class UnitVerification(BaseModel):
    """Verification of individual unit."""
    
    unit_identifier: str  # "Flat 1", "Ground Floor", etc.
    
    # Self-containment check
    has_own_entrance: Optional[bool] = None
    has_own_kitchen: Optional[bool] = None
    has_own_bathroom: Optional[bool] = None
    is_self_contained: Optional[bool] = None
    
    # Size and layout
    beds: Optional[int] = None
    floor_area_sqft: Optional[float] = None
    
    # Condition
    condition_rating: Optional[str] = Field(
        None,
        description="good, fair, poor, very_poor"
    )
    refurb_scope: Optional[str] = Field(
        None,
        description="none, cosmetic, light, medium, heavy"
    )
    estimated_refurb_cost: Optional[int] = None
    
    # Tenancy
    currently_let: Optional[bool] = None
    current_rent_pcm: Optional[int] = None
    tenancy_type: Optional[str] = None  # AST, periodic, etc.
    tenant_in_situ: Optional[bool] = None
    
    notes: Optional[str] = None


class PhysicalVerification(BaseModel):
    """Manual input: Physical inspection results."""
    
    # Viewing conducted
    viewing_date: Optional[date] = None
    viewed_by: Optional[str] = None
    
    # Unit details
    units: List[UnitVerification] = []
    total_units_verified: Optional[int] = None
    
    # Building condition
    structural_concerns: List[str] = []
    has_survey: bool = False
    survey_type: Optional[str] = None  # homebuyer, building, specific
    survey_cost: Optional[int] = None
    
    # Shared areas
    common_parts_condition: Optional[str] = None
    shared_facilities: List[str] = []  # Items shared between units
    
    # Boundaries
    boundaries_clear: Optional[bool] = None
    boundary_issues: List[str] = []
    
    # Services
    utilities_separate: Optional[bool] = Field(
        None,
        description="Are utilities separately metered?"
    )
    utility_issues: List[str] = []
    
    notes: Optional[str] = None


# ============================================================================
# FINANCIAL VERIFICATION INPUTS
# ============================================================================

class FinancialVerification(BaseModel):
    """Manual input: Financial verification."""
    
    # Rental income
    total_current_rent_pcm: Optional[int] = None
    rental_schedule_verified: bool = False
    
    # Costs
    known_service_charges: Optional[int] = None
    known_ground_rent: Optional[int] = None
    insurance_cost: Optional[int] = None
    management_cost: Optional[int] = None
    
    # Valuations
    has_formal_valuation: bool = False
    valuation_date: Optional[date] = None
    valuation_amount: Optional[int] = None
    valuation_basis: Optional[str] = None  # market_value, investment, forced_sale
    
    # Individual unit valuations
    individual_valuations: List[dict] = []  # [{unit: str, value: int}]
    
    # Lender position
    existing_debt: Optional[int] = None
    equity_position: Optional[int] = None
    
    notes: Optional[str] = None


# ============================================================================
# COMPLETE MANUAL INPUTS MODEL
# ============================================================================

class ManualInputs(BaseModel):
    """Complete manual inputs for a property."""
    
    property_id: str
    
    title: TitleInputs = TitleInputs()
    planning: PlanningInputs = PlanningInputs()
    physical: Optional[PhysicalVerification] = None
    financial: Optional[FinancialVerification] = None
    
    # Overall manual assessment
    manual_red_flags: List[str] = []
    manual_green_flags: List[str] = []
    
    # Completion tracking
    completion_percentage: float = 0.0
    last_updated: Optional[date] = None
    updated_by: Optional[str] = None
```

---


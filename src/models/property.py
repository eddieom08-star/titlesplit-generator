import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source information
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # rightmove, zoopla, auction
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    # Basic listing data
    title: Mapped[str] = mapped_column(Text, nullable=False)
    asking_price: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    price_qualifier: Mapped[Optional[str]] = mapped_column(String(50))  # guide, offers_over, etc

    # Location
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    postcode: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)

    # Unit information
    estimated_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    unit_breakdown: Mapped[Optional[dict]] = mapped_column(JSON)  # [{beds: 2, sqft: 500}, ...]

    # Title/Tenure (critical for title split)
    tenure: Mapped[str] = mapped_column(String(50), default="unknown", index=True)  # freehold, leasehold, unknown
    tenure_source: Mapped[Optional[str]] = mapped_column(String(50))  # listing, epc, land_registry
    tenure_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    title_number: Mapped[Optional[str]] = mapped_column(String(50))
    is_single_title: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Condition indicators
    avg_epc_rating: Mapped[Optional[str]] = mapped_column(String(1))
    construction_age: Mapped[Optional[str]] = mapped_column(String(50))
    refurb_indicators: Mapped[Optional[dict]] = mapped_column(JSON)

    # Scoring
    title_split_score: Mapped[int] = mapped_column(Integer, default=0, index=True)  # 0-100
    opportunity_score: Mapped[int] = mapped_column(Integer, default=0, index=True)  # 0-100

    # Financial projections
    price_per_unit: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_individual_values: Mapped[Optional[dict]] = mapped_column(JSON)
    estimated_gross_uplift: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_net_uplift: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_split_costs: Mapped[Optional[int]] = mapped_column(Integer)

    # Status
    status: Mapped[str] = mapped_column(String(50), default="new", index=True)  # new, analysing, opportunity, rejected, contacted
    rejection_reasons: Mapped[Optional[dict]] = mapped_column(JSON)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Timestamps
    listed_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_analysed: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    unit_epcs: Mapped[list["UnitEPC"]] = relationship("UnitEPC", back_populates="property", cascade="all, delete-orphan")
    comparables: Mapped[list["Comparable"]] = relationship("Comparable", back_populates="property", cascade="all, delete-orphan")
    analyses: Mapped[list["Analysis"]] = relationship("Analysis", back_populates="property", cascade="all, delete-orphan")
    manual_inputs: Mapped[list["ManualInput"]] = relationship("ManualInput", back_populates="property", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Property {self.address_line1}, {self.postcode} - £{self.asking_price:,}>"


class UnitEPC(Base):
    __tablename__ = "unit_epcs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False, index=True)

    unit_address: Mapped[str] = mapped_column(String(255), nullable=False)
    current_rating: Mapped[str] = mapped_column(String(1), nullable=False)  # A-G
    potential_rating: Mapped[Optional[str]] = mapped_column(String(1))
    floor_area: Mapped[float] = mapped_column(Float, nullable=False)  # sqm
    property_type: Mapped[str] = mapped_column(String(50), nullable=False)  # flat, maisonette
    construction_age_band: Mapped[Optional[str]] = mapped_column(String(50))

    # Additional EPC data
    lodgement_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    lmk_key: Mapped[Optional[str]] = mapped_column(String(100))  # EPC unique key

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="unit_epcs")

    def __repr__(self) -> str:
        return f"<UnitEPC {self.unit_address} - Rating: {self.current_rating}>"


class Comparable(Base):
    __tablename__ = "comparables"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False, index=True)

    address: Mapped[str] = mapped_column(String(255), nullable=False)
    postcode: Mapped[str] = mapped_column(String(10), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    sale_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    beds: Mapped[Optional[int]] = mapped_column(Integer)
    property_type: Mapped[str] = mapped_column(String(50), nullable=False)  # flat, house
    distance_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # land_registry, rightmove_sold

    # Additional data
    floor_area_sqm: Mapped[Optional[float]] = mapped_column(Float)
    price_per_sqm: Mapped[Optional[float]] = mapped_column(Float)
    time_adjusted_price: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="comparables")

    def __repr__(self) -> str:
        return f"<Comparable {self.address} - £{self.price:,}>"


class ManualInput(Base):
    """Manual verification data entered by user to improve analysis."""
    __tablename__ = "manual_inputs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False, index=True)

    # Title Verification
    verified_tenure: Mapped[Optional[str]] = mapped_column(String(50))  # freehold, leasehold
    title_number: Mapped[Optional[str]] = mapped_column(String(50))
    is_single_title: Mapped[Optional[bool]] = mapped_column(Boolean)
    title_verified_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    title_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Unit Verification
    verified_units: Mapped[Optional[int]] = mapped_column(Integer)
    unit_breakdown: Mapped[Optional[dict]] = mapped_column(JSON)  # [{beds: 2, sqft: 500, floor: 1}, ...]
    units_verified_date: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Planning Status
    planning_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    planning_applications: Mapped[Optional[dict]] = mapped_column(JSON)
    planning_constraints: Mapped[Optional[dict]] = mapped_column(JSON)  # conservation, listed, article4
    planning_notes: Mapped[Optional[str]] = mapped_column(Text)

    # HMO/Licensing
    hmo_license_required: Mapped[Optional[bool]] = mapped_column(Boolean)
    hmo_license_status: Mapped[Optional[str]] = mapped_column(String(50))  # licensed, pending, not_required, unknown
    additional_licensing: Mapped[Optional[dict]] = mapped_column(JSON)

    # Physical Inspection
    site_visited: Mapped[bool] = mapped_column(Boolean, default=False)
    site_visit_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    condition_rating: Mapped[Optional[str]] = mapped_column(String(20))  # excellent, good, fair, poor
    access_issues: Mapped[Optional[str]] = mapped_column(Text)
    structural_concerns: Mapped[Optional[str]] = mapped_column(Text)

    # Financial Adjustments
    revised_asking_price: Mapped[Optional[int]] = mapped_column(Integer)
    additional_costs_identified: Mapped[Optional[dict]] = mapped_column(JSON)
    negotiation_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Deal Blockers
    blockers: Mapped[Optional[dict]] = mapped_column(JSON)  # [{type: "title", reason: "leasehold"}]
    deal_status: Mapped[str] = mapped_column(String(50), default="active")  # active, blocked, passed, completed

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="manual_inputs")

    def __repr__(self) -> str:
        return f"<ManualInput property={self.property_id} status={self.deal_status}>"


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False, index=True)

    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)  # initial, detailed, manual

    # Section 1: Title Structure (from framework)
    title_structure_score: Mapped[int] = mapped_column(Integer, default=0)
    title_structure_notes: Mapped[Optional[dict]] = mapped_column(JSON)

    # Section 2: Strategic rationale
    exit_strategy_score: Mapped[int] = mapped_column(Integer, default=0)
    financing_benefit_score: Mapped[int] = mapped_column(Integer, default=0)

    # Section 5: Cost-benefit
    estimated_costs: Mapped[Optional[dict]] = mapped_column(JSON)
    estimated_benefits: Mapped[Optional[dict]] = mapped_column(JSON)
    net_benefit_per_unit: Mapped[Optional[int]] = mapped_column(Integer)

    # Section 6: Risk assessment
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_factors: Mapped[Optional[dict]] = mapped_column(JSON)

    # AI Analysis (Claude)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_risk_flags: Mapped[Optional[dict]] = mapped_column(JSON)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)

    # Recommendation
    recommendation: Mapped[str] = mapped_column(String(50), default="pending")  # proceed, review, decline
    recommendation_rationale: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="analyses")

    def __repr__(self) -> str:
        return f"<Analysis {self.analysis_type} - {self.recommendation}>"

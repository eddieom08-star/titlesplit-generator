## CHUNK 16: Recommendation Update Engine

### 16.1 Recalculating Recommendation After Manual Inputs

```python
# src/analysis/recommendation_engine.py

from typing import List, Optional
from .impact_rules import Impact, ImpactType, assess_charge_impact, assess_covenant_impact
from .impact_rules import assess_hmo_licensing_impact, assess_physical_impact
from .impact_rules import TITLE_IMPACT_RULES, PLANNING_IMPACT_RULES


class RecommendationEngine:
    """
    Engine to calculate and update recommendations based on all available data.
    """
    
    def __init__(self, property: Property, manual_inputs: Optional[ManualInputs] = None):
        self.property = property
        self.manual_inputs = manual_inputs or ManualInputs(property_id=str(property.id))
        self.impacts: List[Impact] = []
    
    def calculate_all_impacts(self) -> List[Impact]:
        """Calculate impacts from all manual inputs."""
        
        self.impacts = []
        
        # === TITLE IMPACTS ===
        if self.manual_inputs.title.verification:
            v = self.manual_inputs.title.verification
            
            # Tenure
            if v.tenure_confirmed and v.tenure_confirmed in TITLE_IMPACT_RULES["tenure_confirmed"]:
                self.impacts.append(TITLE_IMPACT_RULES["tenure_confirmed"][v.tenure_confirmed])
            
            # Single title
            if v.is_single_title is not None:
                self.impacts.append(TITLE_IMPACT_RULES["is_single_title"][v.is_single_title])
            
            # Title class
            if v.title_class and v.title_class in TITLE_IMPACT_RULES["title_class"]:
                self.impacts.append(TITLE_IMPACT_RULES["title_class"][v.title_class])
        
        # Charges
        for charge in self.manual_inputs.title.charges:
            self.impacts.append(assess_charge_impact(charge))
        
        # Covenants
        for covenant in self.manual_inputs.title.covenants:
            self.impacts.append(assess_covenant_impact(covenant))
        
        # === PLANNING IMPACTS ===
        if self.manual_inputs.planning.planning_status:
            ps = self.manual_inputs.planning.planning_status
            
            # Use class
            if ps.current_use_class and ps.current_use_class in PLANNING_IMPACT_RULES["current_use_class"]:
                self.impacts.append(PLANNING_IMPACT_RULES["current_use_class"][ps.current_use_class])
            
            # Conversion consent
            if ps.original_conversion_consented is not None:
                self.impacts.append(
                    PLANNING_IMPACT_RULES["original_conversion_consented"][ps.original_conversion_consented]
                )
            
            # Building regs
            if ps.building_regs_signed_off is not None:
                self.impacts.append(
                    PLANNING_IMPACT_RULES["building_regs_signed_off"][ps.building_regs_signed_off]
                )
            
            # Article 4
            if ps.in_article_4_area is not None:
                self.impacts.append(
                    PLANNING_IMPACT_RULES["in_article_4_area"][ps.in_article_4_area]
                )
        
        # HMO licensing
        if self.manual_inputs.planning.hmo_licensing:
            self.impacts.extend(
                assess_hmo_licensing_impact(self.manual_inputs.planning.hmo_licensing)
            )
        
        # === PHYSICAL IMPACTS ===
        if self.manual_inputs.physical:
            self.impacts.extend(
                assess_physical_impact(self.manual_inputs.physical)
            )
        
        return self.impacts
    
    def generate_updated_recommendation(self) -> Recommendation:
        """Generate updated recommendation incorporating all impacts."""
        
        # Calculate impacts
        self.calculate_all_impacts()
        
        # Check for blockers
        blockers = [i for i in self.impacts if i.impact_type == ImpactType.BLOCKER]
        if blockers:
            return Recommendation(
                level=RecommendationLevel.DECLINE,
                stage=self._determine_stage(),
                confidence=0.95,  # High confidence in decline
                headline=f"DECLINE: {blockers[0].headline}",
                summary=(
                    f"This opportunity has a deal-breaking issue: {blockers[0].explanation[:200]}... "
                    f"Do not proceed with this acquisition."
                ),
                positive_factors=self._get_positive_factors(),
                negative_factors=self._get_negative_factors(),
                unknown_factors=self._get_unknown_factors(),
                hard_blockers=[b.headline for b in blockers],
                soft_blockers=[],
                required_actions=blockers[0].required_actions,
                optional_actions=[],
                estimated_net_benefit=None,
                benefit_confidence="n/a",
                risk_level="blocked"
            )
        
        # Calculate aggregate score
        base_score = self.property.opportunity_score or 50
        impact_adjustment = sum(i.impact_score for i in self.impacts)
        adjusted_score = max(0, min(100, base_score + impact_adjustment))
        
        # Calculate total cost and time impacts
        total_cost_impact = sum(i.cost_impact or 0 for i in self.impacts)
        total_time_impact = sum(i.time_impact_weeks or 0 for i in self.impacts)
        
        # Adjust benefit calculation
        original_benefit = self.property.estimated_net_uplift or 0
        adjusted_benefit = original_benefit - total_cost_impact
        
        # Determine recommendation level
        level = self._determine_level(adjusted_score, adjusted_benefit)
        
        # Determine confidence based on data completeness
        confidence = self._calculate_confidence()
        
        return Recommendation(
            level=level,
            stage=self._determine_stage(),
            confidence=confidence,
            headline=self._generate_headline(level, adjusted_score),
            summary=self._generate_summary(level, adjusted_benefit, total_time_impact),
            positive_factors=self._get_positive_factors(),
            negative_factors=self._get_negative_factors(),
            unknown_factors=self._get_unknown_factors(),
            hard_blockers=[],
            soft_blockers=[i.headline for i in self.impacts if i.impact_type == ImpactType.MAJOR_NEGATIVE],
            required_actions=self._aggregate_required_actions(),
            optional_actions=self._aggregate_optional_actions(),
            estimated_net_benefit=adjusted_benefit if adjusted_benefit > 0 else None,
            benefit_confidence="high" if confidence > 0.7 else "medium" if confidence > 0.5 else "low",
            risk_level=self._assess_risk_level()
        )
    
    def _determine_stage(self) -> RecommendationStage:
        """Determine what stage of verification we're at."""
        
        title_verified = (
            self.manual_inputs.title.verification and 
            self.manual_inputs.title.verification.tenure_confirmed
        )
        planning_verified = (
            self.manual_inputs.planning.planning_status and
            self.manual_inputs.planning.planning_status.use_class_verified
        )
        physical_verified = self.manual_inputs.physical is not None
        
        if title_verified and planning_verified and physical_verified:
            return RecommendationStage.FULLY_VERIFIED
        elif title_verified or planning_verified:
            return RecommendationStage.PARTIALLY_VERIFIED
        elif self.property.last_enriched:
            return RecommendationStage.ENRICHED
        else:
            return RecommendationStage.INITIAL
    
    def _determine_level(self, score: int, net_benefit: int) -> RecommendationLevel:
        """Determine recommendation level from score and benefit."""
        
        # Framework Go/No-Go: Net benefit >£2k per unit
        benefit_per_unit = 0
        if self.property.estimated_units and self.property.estimated_units > 0:
            benefit_per_unit = net_benefit / self.property.estimated_units
        
        meets_threshold = benefit_per_unit >= 2000
        
        if score >= 85 and meets_threshold:
            return RecommendationLevel.STRONG_PROCEED
        elif score >= 70 and meets_threshold:
            return RecommendationLevel.PROCEED
        elif score >= 60 and net_benefit > 0:
            return RecommendationLevel.PROCEED_WITH_CAUTION
        elif score >= 50:
            return RecommendationLevel.REVIEW_REQUIRED
        elif score >= 40:
            return RecommendationLevel.LIKELY_DECLINE
        else:
            return RecommendationLevel.DECLINE
    
    def _calculate_confidence(self) -> float:
        """Calculate confidence based on data completeness."""
        
        confidence = 0.3  # Base confidence
        
        # Add for EPC data
        if self.property.avg_epc_rating:
            confidence += 0.1
        
        # Add for title verification
        if self.manual_inputs.title.verification:
            if self.manual_inputs.title.verification.tenure_confirmed:
                confidence += 0.2
            if self.manual_inputs.title.verification.is_single_title is not None:
                confidence += 0.1
        
        # Add for planning verification  
        if self.manual_inputs.planning.planning_status:
            if self.manual_inputs.planning.planning_status.use_class_verified:
                confidence += 0.1
        
        # Add for physical verification
        if self.manual_inputs.physical:
            confidence += 0.1
            if self.manual_inputs.physical.units:
                confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _get_positive_factors(self) -> List[str]:
        """Get all positive factors from impacts."""
        return [
            i.headline for i in self.impacts 
            if i.impact_type in [ImpactType.ENABLER, ImpactType.MAJOR_POSITIVE, ImpactType.MINOR_POSITIVE]
        ]
    
    def _get_negative_factors(self) -> List[str]:
        """Get all negative factors from impacts."""
        return [
            i.headline for i in self.impacts
            if i.impact_type in [ImpactType.MAJOR_NEGATIVE, ImpactType.MINOR_NEGATIVE]
        ]
    
    def _get_unknown_factors(self) -> List[str]:
        """Get factors that still need verification."""
        unknown = []
        
        if not self.manual_inputs.title.verification:
            unknown.append("Title not verified - need Land Registry search")
        elif not self.manual_inputs.title.verification.tenure_confirmed:
            unknown.append("Tenure not confirmed from title")
        
        if not self.manual_inputs.planning.planning_status:
            unknown.append("Planning status not verified")
        
        if not self.manual_inputs.physical:
            unknown.append("Physical inspection not completed")
        
        return unknown
    
    def _assess_risk_level(self) -> str:
        """Assess overall risk level."""
        
        major_negatives = len([
            i for i in self.impacts 
            if i.impact_type == ImpactType.MAJOR_NEGATIVE
        ])
        minor_negatives = len([
            i for i in self.impacts
            if i.impact_type == ImpactType.MINOR_NEGATIVE
        ])
        
        if major_negatives >= 3:
            return "very_high"
        elif major_negatives >= 2 or (major_negatives >= 1 and minor_negatives >= 3):
            return "high"
        elif major_negatives >= 1 or minor_negatives >= 3:
            return "medium"
        else:
            return "low"
    
    def _aggregate_required_actions(self) -> List[str]:
        """Aggregate all required actions from impacts."""
        actions = []
        for impact in self.impacts:
            actions.extend(impact.required_actions)
        return list(set(actions))  # Deduplicate
    
    def _aggregate_optional_actions(self) -> List[str]:
        """Aggregate all mitigation options as optional actions."""
        options = []
        for impact in self.impacts:
            options.extend(impact.mitigation_options)
        return list(set(options))
    
    def _generate_headline(self, level: RecommendationLevel, score: int) -> str:
        """Generate recommendation headline."""
        
        headlines = {
            RecommendationLevel.STRONG_PROCEED: f"Strong opportunity (score {score}) - proceed to acquisition",
            RecommendationLevel.PROCEED: f"Good opportunity (score {score}) - proceed with standard DD",
            RecommendationLevel.PROCEED_WITH_CAUTION: f"Viable with caveats (score {score}) - additional DD required",
            RecommendationLevel.REVIEW_REQUIRED: f"Uncertain (score {score}) - more information needed",
            RecommendationLevel.LIKELY_DECLINE: f"Marginal opportunity (score {score}) - likely not viable",
            RecommendationLevel.DECLINE: f"Not recommended (score {score}) - significant issues",
        }
        return headlines.get(level, f"Score: {score}")
    
    def _generate_summary(self, level: RecommendationLevel, net_benefit: int, time_weeks: int) -> str:
        """Generate recommendation summary."""
        
        benefit_text = f"Estimated net benefit: £{net_benefit:,}" if net_benefit > 0 else "Net benefit uncertain"
        time_text = f"Estimated additional time: {time_weeks} weeks" if time_weeks > 0 else ""
        
        stage = self._determine_stage()
        
        if level in [RecommendationLevel.STRONG_PROCEED, RecommendationLevel.PROCEED]:
            return (
                f"This property shows strong potential for title splitting. {benefit_text}. "
                f"Verified factors support the opportunity. {time_text}"
            )
        elif level == RecommendationLevel.PROCEED_WITH_CAUTION:
            negatives = self._get_negative_factors()
            return (
                f"The opportunity is viable but has issues requiring attention: {', '.join(negatives[:2])}. "
                f"{benefit_text}. Factor additional costs and time into your decision."
            )
        elif level == RecommendationLevel.REVIEW_REQUIRED:
            unknowns = self._get_unknown_factors()
            return (
                f"Cannot make confident recommendation due to missing information: {', '.join(unknowns[:2])}. "
                f"Complete verification before proceeding."
            )
        else:
            negatives = self._get_negative_factors()
            return (
                f"This opportunity has significant issues: {', '.join(negatives[:2])}. "
                f"The risk/reward balance does not favour proceeding."
            )
```

---


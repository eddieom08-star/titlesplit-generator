from dataclasses import dataclass
from typing import Optional

# Cost model (per property unless noted)
COST_MODEL = {
    # Legal costs
    "solicitor_per_unit": {
        "min": 300,
        "max": 600,
        "typical": 450,
    },
    # Land Registry fees (based on value bands - 2024 rates)
    "land_registry_fees": {
        "bands": [
            (0, 80000, 20),
            (80001, 100000, 40),
            (100001, 200000, 95),
            (200001, 500000, 135),
            (500001, 1000000, 270),
            (1000001, float('inf'), 455),
        ]
    },
    # Title plan preparation
    "title_plan_per_unit": {
        "min": 100,
        "max": 300,
        "typical": 200,
    },
    # Lender costs (one-off)
    "lender_consent_fee": {
        "min": 500,
        "max": 2500,
        "typical": 1000,
    },
    "lender_legal_costs": {
        "min": 500,
        "max": 2000,
        "typical": 1000,
    },
    # Valuations
    "valuation_per_unit": {
        "min": 150,
        "max": 350,
        "typical": 250,
    },
    # Insurance
    "insurance_endorsement_per_unit": {
        "min": 50,
        "max": 100,
        "typical": 75,
    },
    # Contingency
    "contingency_percent": 10,
}


@dataclass
class CostEstimate:
    solicitor_fees: int
    title_plans: int
    valuations: int
    insurance: int
    land_registry: int
    lender_consent: int
    lender_legal: int
    subtotal: int
    contingency: int
    total: int
    per_unit: int
    breakdown: dict


@dataclass
class BenefitEstimate:
    current_portfolio_value: int
    individual_values_aggregate: int
    gross_uplift: int
    gross_uplift_percent: float
    transaction_costs: int
    net_uplift: int
    net_uplift_percent: float
    net_benefit_per_unit: int
    meets_threshold: bool
    cost_ratio: float
    cost_ratio_acceptable: bool


@dataclass
class CostBenefitAnalysis:
    costs: CostEstimate
    benefits: BenefitEstimate
    recommendation: str
    rationale: str


def get_land_registry_fee(value: int) -> int:
    """Get Land Registry registration fee for a property value."""
    for min_val, max_val, fee in COST_MODEL["land_registry_fees"]["bands"]:
        if min_val <= value <= max_val:
            return fee
    return 455  # Max fee


def estimate_split_costs(
    num_units: int,
    individual_values: list[int],
    scenario: str = "typical",  # "min", "typical", "max"
) -> CostEstimate:
    """
    Estimate total title splitting costs.

    Returns detailed breakdown per Framework Section 5.
    """
    # Get cost variant
    def get_cost(item: str) -> int:
        return COST_MODEL[item][scenario]

    # Per-unit costs
    solicitor_fees = num_units * get_cost("solicitor_per_unit")
    title_plans = num_units * get_cost("title_plan_per_unit")
    valuations = num_units * get_cost("valuation_per_unit")
    insurance = num_units * get_cost("insurance_endorsement_per_unit")

    # Land Registry fees (per unit based on value)
    land_registry = sum(get_land_registry_fee(v) for v in individual_values)

    # One-off costs
    lender_consent = get_cost("lender_consent_fee")
    lender_legal = get_cost("lender_legal_costs")

    # Subtotal
    subtotal = (
        solicitor_fees + title_plans + valuations + insurance +
        land_registry + lender_consent + lender_legal
    )

    # Contingency
    contingency = int(subtotal * COST_MODEL["contingency_percent"] / 100)

    # Total
    total = subtotal + contingency

    return CostEstimate(
        solicitor_fees=solicitor_fees,
        title_plans=title_plans,
        valuations=valuations,
        insurance=insurance,
        land_registry=land_registry,
        lender_consent=lender_consent,
        lender_legal=lender_legal,
        subtotal=subtotal,
        contingency=contingency,
        total=total,
        per_unit=total // num_units if num_units > 0 else 0,
        breakdown={
            "solicitor_fees": solicitor_fees,
            "title_plans": title_plans,
            "valuations": valuations,
            "insurance": insurance,
            "land_registry": land_registry,
            "lender_consent": lender_consent,
            "lender_legal": lender_legal,
            "contingency": contingency,
        },
    )


def estimate_split_benefits(
    asking_price: int,
    num_units: int,
    individual_values: list[int],
    split_costs: CostEstimate,
) -> BenefitEstimate:
    """
    Calculate expected benefits from title split.

    Based on Framework Section 5 and Go/No-Go criteria.
    """
    # Aggregate individual values
    aggregate_value = sum(individual_values)

    # Gross uplift
    gross_uplift = aggregate_value - asking_price
    gross_uplift_percent = round((gross_uplift / asking_price) * 100, 1) if asking_price > 0 else 0

    # Net uplift (after costs)
    net_uplift = gross_uplift - split_costs.total
    net_uplift_percent = round((net_uplift / asking_price) * 100, 1) if asking_price > 0 else 0

    # Per unit metrics
    net_benefit_per_unit = net_uplift // num_units if num_units > 0 else 0

    # Framework Go/No-Go thresholds
    cost_ratio = round((split_costs.total / asking_price) * 100, 1) if asking_price > 0 else 0

    return BenefitEstimate(
        current_portfolio_value=asking_price,
        individual_values_aggregate=aggregate_value,
        gross_uplift=gross_uplift,
        gross_uplift_percent=gross_uplift_percent,
        transaction_costs=split_costs.total,
        net_uplift=net_uplift,
        net_uplift_percent=net_uplift_percent,
        net_benefit_per_unit=net_benefit_per_unit,
        meets_threshold=net_benefit_per_unit >= 2000,
        cost_ratio=cost_ratio,
        cost_ratio_acceptable=cost_ratio <= 3.0,
    )


def analyze_cost_benefit(
    asking_price: int,
    num_units: int,
    individual_values: list[int],
) -> CostBenefitAnalysis:
    """
    Run full cost-benefit analysis.

    Returns recommendation based on Framework Go/No-Go criteria.
    """
    # Calculate costs (typical scenario)
    costs = estimate_split_costs(num_units, individual_values, "typical")

    # Calculate benefits
    benefits = estimate_split_benefits(asking_price, num_units, individual_values, costs)

    # Determine recommendation
    if benefits.meets_threshold and benefits.cost_ratio_acceptable:
        if benefits.net_benefit_per_unit >= 5000:
            recommendation = "PROCEED"
            rationale = (
                f"Strong opportunity with £{benefits.net_benefit_per_unit:,} net benefit per unit. "
                f"Gross uplift of {benefits.gross_uplift_percent}% with acceptable cost ratio."
            )
        else:
            recommendation = "PROCEED"
            rationale = (
                f"Viable opportunity with £{benefits.net_benefit_per_unit:,} net benefit per unit. "
                f"Meets minimum threshold of £2,000 per unit."
            )
    elif benefits.gross_uplift_percent >= 15 and not benefits.cost_ratio_acceptable:
        recommendation = "REVIEW"
        rationale = (
            f"Good gross uplift of {benefits.gross_uplift_percent}% but cost ratio of "
            f"{benefits.cost_ratio}% exceeds 3% threshold. Negotiate on price."
        )
    elif benefits.net_benefit_per_unit > 0 and benefits.net_benefit_per_unit < 2000:
        recommendation = "REVIEW"
        rationale = (
            f"Marginal benefit of £{benefits.net_benefit_per_unit:,} per unit. "
            f"May have strategic value but below standard threshold."
        )
    else:
        recommendation = "DECLINE"
        rationale = (
            f"Transaction costs exceed benefit. Net uplift: £{benefits.net_uplift:,}. "
            f"Does not meet investment criteria."
        )

    return CostBenefitAnalysis(
        costs=costs,
        benefits=benefits,
        recommendation=recommendation,
        rationale=rationale,
    )


def calculate_break_even_price(
    individual_values: list[int],
    num_units: int,
    target_net_per_unit: int = 2000,
) -> int:
    """
    Calculate the maximum purchase price to achieve target net benefit per unit.
    """
    aggregate_value = sum(individual_values)
    costs = estimate_split_costs(num_units, individual_values, "typical")

    # Target: (aggregate - price - costs) / num_units >= target
    # Rearranging: price <= aggregate - costs - (target * num_units)
    max_price = aggregate_value - costs.total - (target_net_per_unit * num_units)

    return max(0, max_price)

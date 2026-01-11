## CHUNK 6: AI Analysis Engine

### 6.1 Initial Screening (Fast)

**Purpose:** Quick pass/fail based on extracted data, no AI call required.

```python
# src/analysis/screening.py

def initial_screen(property: Property) -> tuple[bool, list[str]]:
    """
    Fast screening based on hard criteria.
    
    Returns: (passes_screen, rejection_reasons)
    """
    rejections = []
    
    # Must have estimated units
    if not property.estimated_units or property.estimated_units < 2:
        rejections.append("unit_count_unclear")
    
    if property.estimated_units and property.estimated_units > 10:
        rejections.append("too_many_units")
    
    # Must be freehold or unknown (not confirmed leasehold)
    if property.tenure == "leasehold":
        rejections.append("confirmed_leasehold")
    
    if property.tenure == "share_of_freehold":
        rejections.append("share_of_freehold")
    
    # Price per unit sanity check
    if property.price_per_unit:
        if property.price_per_unit > 150000:  # Too expensive for title split play
            rejections.append("price_per_unit_too_high")
        if property.price_per_unit < 20000:  # Suspiciously cheap
            rejections.append("price_per_unit_suspicious")
    
    # Red flags from description
    for flag, category in RED_FLAGS:
        if flag in property.description.lower():
            rejections.append(f"red_flag_{category}")
    
    return len(rejections) == 0, rejections
```

### 6.2 Detailed AI Analysis

**Purpose:** Deep analysis using Claude to extract nuanced information and score opportunity.

```python
# src/analysis/ai_analysis.py

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

**Analyse and respond with JSON:**
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
        "epc_improvement_potential": <bool if EPC D or below>
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
}}
"""
```

### 6.3 Scoring Algorithm

```python
# src/analysis/scoring.py

def calculate_opportunity_score(
    property: Property,
    analysis: AIAnalysis,
    epcs: list[EPCRecord],
    comparables: list[Comparable]
) -> int:
    """
    Calculate composite opportunity score (0-100).
    
    Weighting based on Title Splitting Framework priorities:
    - Title/Tenure suitability: 30%
    - Financial upside: 25%
    - Condition/Refurb opportunity: 20%
    - Risk factors: 15%
    - Data confidence: 10%
    """
    score = 0
    
    # 1. Title/Tenure (30 points max)
    tenure_score = 0
    if analysis.tenure_analysis.likely_tenure == "freehold":
        tenure_score += 20
        if analysis.tenure_analysis.tenure_confidence > 0.8:
            tenure_score += 5
    if analysis.tenure_analysis.single_title_likely:
        tenure_score += 5
    score += min(tenure_score, 30)
    
    # 2. Financial upside (25 points max)
    financial_score = 0
    if analysis.financial_analysis.estimated_gross_uplift_percent:
        uplift = analysis.financial_analysis.estimated_gross_uplift_percent
        if uplift >= 30:
            financial_score = 25
        elif uplift >= 20:
            financial_score = 20
        elif uplift >= 15:
            financial_score = 15
        elif uplift >= 10:
            financial_score = 10
    score += financial_score
    
    # 3. Condition/Refurb opportunity (20 points max)
    condition_score = 0
    if analysis.condition_analysis.refurb_needed:
        condition_score += 10
        if analysis.condition_analysis.refurb_scope in ["medium", "heavy"]:
            condition_score += 5
    if epcs:
        avg_rating = calculate_avg_epc_rating(epcs)
        if avg_rating in ["E", "F", "G"]:
            condition_score += 5
        elif avg_rating == "D":
            condition_score += 3
    score += min(condition_score, 20)
    
    # 4. Risk factors (15 points max, start at 15 and deduct)
    risk_score = 15
    risk_score -= len(analysis.risk_analysis.red_flags) * 5
    risk_score -= len(analysis.risk_analysis.amber_flags) * 2
    score += max(risk_score, 0)
    
    # 5. Data confidence (10 points max)
    confidence_score = 0
    if analysis.unit_analysis.unit_confidence > 0.8:
        confidence_score += 3
    if analysis.tenure_analysis.tenure_confidence > 0.8:
        confidence_score += 3
    if len(epcs) >= property.estimated_units:
        confidence_score += 2
    if len(comparables) >= 3:
        confidence_score += 2
    score += min(confidence_score, 10)
    
    return min(score, 100)
```

---


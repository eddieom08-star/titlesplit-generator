## CHUNK 20: Lender Report Generation

### 20.1 GDV Report for Lenders

```python
# src/reports/gdv_report.py

from typing import List
from datetime import datetime
from pydantic import BaseModel


class LenderGDVReport:
    """
    Generate professional GDV reports for lender presentations.
    
    Format matches what bridge lenders and development finance
    providers expect to see.
    """
    
    @staticmethod
    def generate_report(gdv: BlockGDVReport) -> dict:
        """
        Generate a structured report suitable for lender submission.
        
        Sections:
        1. Executive Summary
        2. Property Overview
        3. Valuation Methodology
        4. Unit-by-Unit Analysis
        5. Comparable Evidence
        6. Market Context
        7. Risk Factors
        8. Appendices
        """
        
        return {
            "report_type": "GDV Assessment - Title Split Opportunity",
            "report_date": datetime.now().strftime("%d %B %Y"),
            "report_reference": f"GDV-{datetime.now().strftime('%Y%m%d')}-001",
            
            "executive_summary": {
                "property_address": gdv.property_address,
                "postcode": gdv.postcode,
                "current_asking_price": f"£{gdv.asking_price:,}",
                "number_of_units": gdv.total_units,
                "total_gdv": f"£{gdv.total_gdv:,}",
                "gdv_range": f"£{gdv.gdv_range_low:,} - £{gdv.gdv_range_high:,}",
                "gross_uplift": f"£{gdv.gross_uplift:,} ({gdv.gross_uplift_percent}%)",
                "valuation_confidence": gdv.gdv_confidence.value,
                "key_finding": _generate_key_finding(gdv),
            },
            
            "property_overview": {
                "total_units": gdv.total_units,
                "total_sqft": f"{gdv.total_sqft:,.0f} sqft" if gdv.total_sqft else "TBC",
                "unit_breakdown": [
                    {
                        "unit": u.unit_identifier,
                        "beds": u.beds,
                        "sqft": u.sqft,
                        "epc": u.epc_rating,
                    }
                    for u in gdv.unit_valuations
                ],
            },
            
            "valuation_methodology": {
                "approach": "Multi-source comparable analysis with AVM validation",
                "primary_sources": gdv.data_sources,
                "data_freshness": gdv.data_freshness,
                "methodology_notes": """
                    Valuations derived from Land Registry Price Paid data,
                    validated against PropertyData automated valuations.
                    Prices time-adjusted using UK House Price Index.
                    £/sqft analysis used where floor areas available.
                """,
            },
            
            "unit_valuations": [
                {
                    "unit": u.unit_identifier,
                    "bedrooms": u.beds,
                    "sqft": u.sqft,
                    "estimated_value": f"£{u.estimated_value:,}",
                    "value_range": f"£{u.value_range_low:,} - £{u.value_range_high:,}",
                    "price_per_sqft": f"£{u.price_per_sqft_used:,.0f}" if u.price_per_sqft_used else "N/A",
                    "confidence": u.confidence.value,
                    "valuation_method": u.primary_method,
                    "comparables_count": len(u.comparables_used),
                    "notes": u.valuation_notes,
                }
                for u in gdv.unit_valuations
            ],
            
            "comparable_evidence": {
                "summary": gdv.comparables_summary,
                "top_comparables": [
                    {
                        "address": c.address,
                        "price": f"£{c.price:,}",
                        "date": c.date,
                        "source": c.source.value,
                        "time_adjusted": f"£{c.time_adjusted_price:,}" if c.time_adjusted_price else None,
                    }
                    for c in gdv.unit_valuations[0].comparables_used[:5]
                ] if gdv.unit_valuations else [],
            },
            
            "market_context": {
                "local_gross_yield": f"{gdv.local_market_data.get('gross_yield', 'N/A')}%",
                "average_rent_pcm": f"£{gdv.local_market_data.get('average_rent_pcm', 'N/A'):,}" if isinstance(gdv.local_market_data.get('average_rent_pcm'), (int, float)) else "N/A",
                "price_growth_1y": f"{gdv.local_market_data.get('price_growth_1y', 'N/A')}%",
                "price_growth_5y": f"{gdv.local_market_data.get('price_growth_5y', 'N/A')}%",
                "regional_average_price": f"£{gdv.local_market_data.get('regional_average_price', 'N/A'):,}" if isinstance(gdv.local_market_data.get('regional_average_price'), (int, float)) else "N/A",
            },
            
            "financial_summary": {
                "acquisition_price": f"£{gdv.asking_price:,}",
                "total_gdv_post_split": f"£{gdv.total_gdv:,}",
                "title_split_costs": f"£{gdv.title_split_costs:,}",
                "refurbishment_budget": f"£{gdv.refurbishment_budget:,}" if gdv.refurbishment_budget else "TBC",
                "total_costs": f"£{gdv.total_costs:,}",
                "net_uplift": f"£{gdv.net_uplift:,}",
                "net_uplift_percent": f"{gdv.net_uplift_percent}%",
                "profit_per_unit": f"£{gdv.net_profit_per_unit:,}",
            },
            
            "risk_factors": {
                "valuation_confidence": gdv.gdv_confidence.value,
                "limitations": gdv.limitations,
                "market_risks": [
                    "Property values subject to market conditions",
                    "Individual unit sales depend on buyer demand",
                    "Mortgage availability for buyers may vary",
                ],
                "execution_risks": [
                    "Title split requires Land Registry approval",
                    "Existing lender consent required",
                    "Timeline subject to legal process",
                ],
            },
            
            "confidence_statement": gdv.confidence_statement,
            
            "appendices": {
                "a": "Full comparable sales list",
                "b": "EPC certificates",
                "c": "Title register extract",
                "d": "PropertyData valuation reports",
            },
            
            "disclaimer": """
                This report is provided for indicative purposes only and does not 
                constitute a RICS Red Book valuation. The figures presented are 
                based on publicly available market data and automated valuation 
                models. A formal valuation by a RICS-registered surveyor is 
                recommended before making lending decisions. [Company Name] accepts 
                no liability for decisions made based on this report.
            """,
        }


def _generate_key_finding(gdv: BlockGDVReport) -> str:
    """Generate the key finding for executive summary."""
    
    if gdv.gross_uplift_percent >= 25:
        return f"Strong title split opportunity with {gdv.gross_uplift_percent}% gross uplift potential"
    elif gdv.gross_uplift_percent >= 15:
        return f"Viable title split opportunity with {gdv.gross_uplift_percent}% gross uplift potential"
    elif gdv.gross_uplift_percent >= 10:
        return f"Marginal title split opportunity - {gdv.gross_uplift_percent}% uplift requires careful cost management"
    else:
        return f"Limited uplift potential at {gdv.gross_uplift_percent}% - recommend further analysis"
```

### 20.2 Example GDV Output (Lender Format)

```json
{
  "report_type": "GDV Assessment - Title Split Opportunity",
  "report_date": "11 January 2026",
  "report_reference": "GDV-20260111-001",
  
  "executive_summary": {
    "property_address": "45-47 Stanley Road, Liverpool",
    "postcode": "L4 0TH",
    "current_asking_price": "£285,000",
    "number_of_units": 4,
    "total_gdv": "£380,000",
    "gdv_range": "£342,000 - £418,000",
    "gross_uplift": "£95,000 (33.3%)",
    "valuation_confidence": "medium",
    "key_finding": "Strong title split opportunity with 33.3% gross uplift potential"
  },
  
  "unit_valuations": [
    {
      "unit": "Flat 1 (Ground Floor)",
      "bedrooms": 2,
      "sqft": 650,
      "estimated_value": "£98,000",
      "value_range": "£88,200 - £107,800",
      "price_per_sqft": "£151",
      "confidence": "medium",
      "valuation_method": "comparable + psf",
      "comparables_count": 8,
      "notes": "Based on 8 comparable 2-bed flat sales. PropertyData AVM £95,000 validates estimate."
    },
    {
      "unit": "Flat 2 (Ground Floor)",
      "bedrooms": 1,
      "sqft": 450,
      "estimated_value": "£72,000",
      "value_range": "£64,800 - £79,200",
      "price_per_sqft": "£160",
      "confidence": "medium",
      "valuation_method": "comparable + psf",
      "comparables_count": 6,
      "notes": "1-bed flats in higher demand. Comparable evidence supports premium."
    },
    {
      "unit": "Flat 3 (First Floor)",
      "bedrooms": 2,
      "sqft": 680,
      "estimated_value": "£105,000",
      "value_range": "£94,500 - £115,500",
      "price_per_sqft": "£154",
      "confidence": "high",
      "valuation_method": "comparable + psf",
      "comparables_count": 12,
      "notes": "Strong comparable evidence. First floor typically commands small premium."
    },
    {
      "unit": "Flat 4 (First Floor)",
      "bedrooms": 2,
      "sqft": 620,
      "estimated_value": "£105,000",
      "value_range": "£94,500 - £115,500",
      "price_per_sqft": "£169",
      "confidence": "medium",
      "valuation_method": "comparable + psf",
      "comparables_count": 7,
      "notes": "Slightly smaller unit but good layout. Priced in line with comparables."
    }
  ],
  
  "market_context": {
    "local_gross_yield": "7.2%",
    "average_rent_pcm": "£650",
    "price_growth_1y": "2.3%",
    "price_growth_5y": "18.5%",
    "regional_average_price": "£172,000"
  },
  
  "comparable_evidence": {
    "summary": {
      "total_comparables": 23,
      "land_registry_transactions": 18,
      "average_price_2bed": "£95,000",
      "average_price_1bed": "£68,000",
      "average_psf": "£155"
    },
    "top_comparables": [
      {
        "address": "Flat 3, 52 Stanley Road, L4 0TJ",
        "price": "£92,000",
        "date": "2025-09-15",
        "source": "land_registry_ppd",
        "time_adjusted": "£94,116"
      },
      {
        "address": "Flat 1, 38 Dacy Road, L4 0TB",
        "price": "£97,500",
        "date": "2025-07-22",
        "source": "land_registry_ppd",
        "time_adjusted": "£100,618"
      }
    ]
  },
  
  "financial_summary": {
    "acquisition_price": "£285,000",
    "total_gdv_post_split": "£380,000",
    "title_split_costs": "£12,500",
    "refurbishment_budget": "£20,000",
    "total_costs": "£32,500",
    "net_uplift": "£62,500",
    "net_uplift_percent": "21.9%",
    "profit_per_unit": "£15,625"
  },
  
  "data_sources": [
    "HM Land Registry Price Paid Data (verified transactions)",
    "PropertyData.co.uk Automated Valuation Model",
    "UK House Price Index (time adjustments)",
    "EPC Register (floor areas and ratings)"
  ]
}
```

---


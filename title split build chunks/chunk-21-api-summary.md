## CHUNK 21: API Integration Summary

### 21.1 Data Source Cost Summary

| Source | Endpoint | Cost | Credits/Call | Use Case |
|--------|----------|------|--------------|----------|
| **PropertyData** | /valuation-sale | £28-150/mo | 1 | Per-unit AVM |
| **PropertyData** | /sold-prices | £28-150/mo | 1 | Comparable list |
| **PropertyData** | /sold-prices-per-sqf | £28-150/mo | 1 | £/sqft analysis |
| **PropertyData** | /yields | £28-150/mo | 1 | Yield context |
| **PropertyData** | /floor-areas | £28-150/mo | 1 | Sqft lookup |
| **Land Registry PPD** | SPARQL | Free | N/A | Actual transactions |
| **Land Registry UKHPI** | SPARQL | Free | N/A | Price indices |
| **EPC Open Data** | REST API | Free | N/A | Floor areas, EPCs |

### 21.2 Estimated API Costs Per Analysis

For analysing one block of 4 flats:

| Call | Count | Credits |
|------|-------|---------|
| /valuation-sale | 4 (per unit) | 4 |
| /sold-prices | 1 | 1 |
| /sold-prices-per-sqf | 2 (by beds) | 2 |
| /yields | 1 | 1 |
| /floor-areas | 1 | 1 |
| Land Registry | N/A | 0 |
| EPC | N/A | 0 |
| **Total** | | **9 credits** |

With PropertyData API Starter plan (500 credits/month @ £28):
- **~55 full property analyses per month**
- Cost per analysis: **~£0.50**

### 21.3 Required Environment Variables

```bash
# .env

# PropertyData API
PROPERTY_DATA_API_KEY=your_api_key_here

# EPC Open Data (Base64 encoded email:key)
EPC_API_KEY=your_base64_encoded_key

# Optional: PropertyMarketIntel
PMI_API_KEY=your_pmi_key

# No keys required for:
# - Land Registry Price Paid Data
# - Land Registry UKHPI
```

---

## Summary: Data-Driven GDV for Lenders

The application now produces **lender-grade GDV assessments** using:

| Metric | Source | Credibility |
|--------|--------|-------------|
| **Comparable sales** | Land Registry PPD | ✅ Government verified transactions |
| **Time adjustments** | UK HPI | ✅ ONS official index |
| **£/sqft analysis** | PropertyData + EPC | ✅ Cross-referenced data |
| **AVM validation** | PropertyData | ⚠️ Commercial model (validated) |
| **Floor areas** | EPC Register | ✅ Official certificates |
| **Market context** | Multiple sources | ✅ Diversified data |

**Key for Lender Acceptance:**
1. Primary evidence from Land Registry (indisputable transaction data)
2. Multiple validation methods (comparables + £/sqft + AVM)
3. Clear confidence ratings and limitations
4. Professional report format with data sourcing
5. Time-adjusted values using official HPI

This approach gives lenders the confidence they need to underwrite against the post-split GDV.

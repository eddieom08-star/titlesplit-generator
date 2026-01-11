## CHUNK 11: Data Source Summary Matrix

| Data Point | Source | API Available | Cost | Reliability | Notes |
|------------|--------|---------------|------|-------------|-------|
| **Listing Data** |||||
| Price, address, description | Rightmove/Zoopla | Hidden API (scrape) | Free | High | Rate limit 2s |
| Images, features | Rightmove/Zoopla | Hidden API | Free | High | |
| Agent details | Rightmove/Zoopla | Hidden API | Free | High | |
| Listed date | Rightmove/Zoopla | Hidden API | Medium | May be missing |
| **Unit Information** |||||
| Unit count | Listing text | Text extraction | Free | Medium | AI improves |
| Unit sizes | EPC API | ✅ Yes | Free | High | 5000/day limit |
| Unit EPCs | EPC API | ✅ Yes | Free | High | |
| **Tenure** |||||
| Tenure stated | Listing text | Text extraction | Free | Medium | Often missing |
| Title number | Land Registry | Manual/Paid | £3-15 | High | Not automated |
| Registered owner | Land Registry | Manual/Paid | £3-15 | High | |
| Charges/restrictions | Land Registry | Manual/Paid | £3-15 | High | |
| **Valuation** |||||
| Comparable sales | Land Registry PPD | ✅ Yes | Free | High | 2yr history |
| Recent sold prices | Rightmove Sold | Scrape | Free | High | |
| **Condition** |||||
| EPC rating | EPC API | ✅ Yes | Free | High | |
| Construction age | EPC API | ✅ Yes | Free | High | |
| Refurb needed | Listing text | AI extraction | API cost | Medium | |
| **Planning** |||||
| Planning history | Council portals | ❌ No unified API | Free | N/A | Manual lookup |
| Use class | Council portals | ❌ No | Free | N/A | |
| HMO status | Council portals | ❌ No | Free | N/A | |
| **Risk Factors** |||||
| Flying freehold | Listing text | Text extraction | Free | Low | May not be disclosed |
| Structural issues | Listing text | Text extraction | Free | Low | May not be disclosed |
| Flood risk | EA Flood API | ✅ Yes | Free | High | Optional enrichment |

---


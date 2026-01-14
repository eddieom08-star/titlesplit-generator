const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://titlesplit-api.onrender.com';

export interface Opportunity {
  id: string;
  source_url: string;
  title: string;
  price: number;
  city: string;
  postcode: string;
  estimated_units: number;
  price_per_unit: number;
  opportunity_score: number;
  tenure: string;
  tenure_confidence: number;
  avg_epc: string | null;
  refurb_needed: boolean;
  estimated_gross_uplift_percent: number | null;
  estimated_net_benefit_per_unit: number | null;
  recommendation: string;
  priority: string;
  first_seen: string;
  images: string[];
}

export interface OpportunityFilters {
  minScore?: number;
  maxPrice?: number;
  minUnits?: number;
  maxUnits?: number;
  cities?: string;
  tenure?: string;
  status?: string;
  includeArchived?: boolean;
  sortBy?: 'score' | 'price' | 'date' | 'uplift';
}

export async function getOpportunities(filters: OpportunityFilters = {}): Promise<Opportunity[]> {
  const params = new URLSearchParams();
  params.set('min_score', String(filters.minScore ?? 0));
  if (filters.maxPrice) params.set('max_price', String(filters.maxPrice));
  if (filters.minUnits) params.set('min_units', String(filters.minUnits));
  if (filters.maxUnits) params.set('max_units', String(filters.maxUnits));
  if (filters.cities) params.set('cities', filters.cities);
  if (filters.tenure) params.set('tenure', filters.tenure);
  if (filters.status) params.set('status', filters.status);
  if (filters.includeArchived) params.set('include_archived', 'true');
  if (filters.sortBy) params.set('sort_by', filters.sortBy);

  const res = await fetch(`${API_URL}/api/opportunities?${params.toString()}`, {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error('Failed to fetch opportunities');
  }
  return res.json();
}

export async function getOpportunity(id: string): Promise<Opportunity> {
  const res = await fetch(`${API_URL}/api/opportunities/${id}`, {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error('Failed to fetch opportunity');
  }
  return res.json();
}

export function formatPrice(price: number): string {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'GBP',
    maximumFractionDigits: 0,
  }).format(price);
}

export function getScoreColor(score: number): string {
  if (score >= 80) return 'bg-green-500';
  if (score >= 60) return 'bg-yellow-500';
  if (score >= 40) return 'bg-orange-500';
  return 'bg-red-500';
}

export function getStatusBadge(status: string): { variant: 'default' | 'secondary' | 'destructive' | 'outline', label: string } {
  switch (status) {
    case 'hot':
      return { variant: 'destructive', label: 'Hot' };
    case 'warm':
      return { variant: 'default', label: 'Warm' };
    case 'pending':
      return { variant: 'secondary', label: 'Pending' };
    case 'analysed':
      return { variant: 'outline', label: 'Analysed' };
    default:
      return { variant: 'secondary', label: status };
  }
}

export async function triggerScrape(): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_URL}/api/scraper/trigger`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to trigger scrape');
  }
  return res.json();
}

export async function triggerEnrichment(batchSize: number = 10): Promise<{ status: string; batch_size: number }> {
  const res = await fetch(`${API_URL}/api/scraper/enrich?batch_size=${batchSize}`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to trigger enrichment');
  }
  return res.json();
}

export async function clearDemoData(): Promise<{ status: string; count: number }> {
  const res = await fetch(`${API_URL}/api/scraper/demo`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error('Failed to clear demo data');
  }
  return res.json();
}

export async function archiveProperty(propertyId: string): Promise<{ status: string; property_id: string }> {
  const res = await fetch(`${API_URL}/api/properties/${propertyId}/archive`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to archive property');
  }
  return res.json();
}

export async function restoreProperty(propertyId: string): Promise<{ status: string; property_id: string }> {
  const res = await fetch(`${API_URL}/api/properties/${propertyId}/restore`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to restore property');
  }
  return res.json();
}

export async function deleteProperty(propertyId: string, permanent: boolean = false): Promise<{ status: string; property_id: string }> {
  const res = await fetch(`${API_URL}/api/properties/${propertyId}?permanent=${permanent}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error('Failed to delete property');
  }
  return res.json();
}

export interface AnalysisResult {
  id: string;
  title: string;
  price: number;
  city: string;
  postcode: string;
  estimated_units: number | null;
  tenure: string;
  opportunity_score: number;
  recommendation: string;
  analysis_notes: string[];
  source_url: string;
}

export async function analyzeUrl(url: string): Promise<AnalysisResult> {
  const res = await fetch(`${API_URL}/api/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Analysis failed' }));
    throw new Error(error.detail || 'Failed to analyze URL');
  }
  return res.json();
}

export interface ComparableSale {
  date: string | null;
  address: string | null;
  price: number | null;
  sqf: number | null;
  price_per_sqf: number | null;
  type: string | null;
  tenure: string | null;
}

export interface ValuationResult {
  status: string;
  asking_price: number;
  num_units: number;
  estimated_unit_value: number | null;
  unit_value_low: number | null;
  unit_value_high: number | null;
  unit_value_confidence: string | null;
  total_separated_value: number | null;
  gross_uplift: number | null;
  gross_uplift_percent: number | null;
  estimated_costs: number | null;
  net_uplift: number | null;
  net_per_unit: number | null;
  meets_threshold: boolean | null;
  recommendation: string | null;
  message: string | null;
  // Land Registry / EPC data
  avg_price_per_sqf: number | null;
  comparable_sales: ComparableSale[] | null;
}

// Property Detail & Manual Inputs

export interface ManualInput {
  verified_tenure: string | null;
  title_number: string | null;
  is_single_title: boolean | null;
  title_notes: string | null;
  verified_units: number | null;
  unit_breakdown: object[] | null;
  planning_checked: boolean;
  planning_constraints: Record<string, boolean> | null;
  planning_notes: string | null;
  hmo_license_required: boolean | null;
  hmo_license_status: string | null;
  site_visited: boolean;
  condition_rating: string | null;
  access_issues: string | null;
  structural_concerns: string | null;
  floorplan_filename: string | null;
  floorplan_analysis: FloorplanAnalysis | null;
  floorplan_analyzed_at: string | null;
  revised_asking_price: number | null;
  additional_costs_identified: Record<string, number> | null;
  deal_status: string;
  blockers: object[] | null;
}

export interface PropertyDetail {
  id: string;
  source_url: string;
  title: string;
  asking_price: number;
  city: string;
  postcode: string;
  estimated_units: number;
  tenure: string;
  tenure_confidence: number;
  opportunity_score: number;
  status: string;
  first_seen: string;
  manual_inputs: ManualInput | null;
}

export interface ImpactItem {
  field: string;
  impact_type: string;
  score_adjustment: number;
  message: string;
}

export interface RecalculatedAnalysis {
  property_id: string;
  original_score: number;
  adjusted_score: number;
  original_recommendation: string;
  updated_recommendation: string;
  impacts: ImpactItem[];
  confidence_level: string;
  valuation: ValuationResult | null;
  cost_breakdown: Record<string, number>;
  net_benefit_per_unit: number;
  blockers: object[];
  warnings: string[];
  positives: string[];
}

export async function getPropertyDetail(id: string): Promise<PropertyDetail> {
  const res = await fetch(`${API_URL}/api/properties/${id}`, {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error('Failed to fetch property');
  }
  return res.json();
}

export async function updateManualInput(
  propertyId: string,
  data: Partial<ManualInput>
): Promise<RecalculatedAnalysis> {
  const res = await fetch(`${API_URL}/api/properties/${propertyId}/manual`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Update failed' }));
    throw new Error(error.detail || 'Failed to update manual input');
  }
  return res.json();
}

export async function recalculateAnalysis(propertyId: string): Promise<RecalculatedAnalysis> {
  const res = await fetch(`${API_URL}/api/properties/${propertyId}/recalculate`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to recalculate');
  }
  return res.json();
}

export async function getValuation(
  postcode: string,
  askingPrice: number,
  numUnits: number,
  avgBedrooms: number = 2
): Promise<ValuationResult> {
  const res = await fetch(`${API_URL}/api/analyze/valuation`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      postcode,
      asking_price: askingPrice,
      num_units: numUnits,
      avg_bedrooms: avgBedrooms,
    }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Valuation failed' }));
    throw new Error(error.detail || 'Failed to get valuation');
  }
  return res.json();
}

// ============================================================
// GDV Report Types & Functions
// ============================================================

export interface UnitValuation {
  unit_identifier: string;
  beds: number | null;
  sqft: number | null;
  epc_rating: string | null;
  estimated_value: number;
  value_range_low: number;
  value_range_high: number;
  confidence: string;
  primary_method: string;
  price_per_sqft_used: number | null;
  valuation_notes: string;
}

export interface GDVReport {
  property_address: string;
  postcode: string;
  title_number: string | null;
  asking_price: number;
  total_units: number;
  total_sqft: number | null;

  // Unit valuations
  unit_valuations: UnitValuation[];

  // GDV summary
  total_gdv: number;
  gdv_range_low: number;
  gdv_range_high: number;
  gdv_confidence: string;

  // Uplift analysis
  gross_uplift: number;
  gross_uplift_percent: number;
  title_split_costs: number;
  refurbishment_budget: number | null;
  total_costs: number;
  net_uplift: number;
  net_uplift_percent: number;
  net_profit_per_unit: number;

  // Market context
  local_market_data: Record<string, unknown>;
  comparables_summary: {
    count: number;
    price_range?: string;
    average?: number;
    median?: number;
    message?: string;
  };
  comparables: {
    address: string;
    postcode: string;
    price: number;
    sale_date: string;
    property_type: string;
    tenure: string;
    land_registry_url: string;
  }[];

  // Report metadata
  data_sources: string[];
  data_freshness: string;
  confidence_statement: string;
  limitations: string[];
  report_date: string;
}

export interface UnitInput {
  id: string;
  beds?: number;
  sqft?: number;
  epc?: string;
}

export interface GDVReportRequest {
  units?: UnitInput[];
  refurbishment_budget?: number;
  title_number?: string;
}

export async function generateGDVReport(
  propertyId: string,
  request: GDVReportRequest = {}
): Promise<GDVReport> {
  // Add 90 second timeout (Render cold starts + Land Registry API calls)
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90000);

  try {
    const res = await fetch(`${API_URL}/api/properties/${propertyId}/gdv-report`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'GDV report generation failed' }));
      throw new Error(error.detail || 'Failed to generate GDV report');
    }
    return res.json();
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('Request timed out - please try again (server may be starting up)');
    }
    throw err;
  }
}

// ============================================================
// Floorplan Analysis Types & Functions
// ============================================================

export interface FloorplanUnit {
  unit_id: string;
  layout_type: string;
  bedrooms: number;
  bathrooms: number;
  reception_rooms: number;
  has_kitchen: boolean;
  estimated_sqft: number | null;
  notes: string;
}

export interface FloorplanAnalysis {
  units_detected: number;
  confidence: number;
  units: FloorplanUnit[];
  self_contained_assessment: {
    all_self_contained: boolean;
    concerns: string[];
    evidence: string;
  };
  layout_concerns: string[];
  suitable_for_title_split: boolean;
  analysis_notes: string;
  analyzed_at: string;
}

export async function uploadFloorplan(
  propertyId: string,
  file: File
): Promise<FloorplanAnalysis> {
  const formData = new FormData();
  formData.append('file', file);

  // 60 second timeout for Claude Vision analysis
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 60000);

  try {
    const res = await fetch(`${API_URL}/api/properties/${propertyId}/floorplan`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Floorplan analysis failed' }));
      throw new Error(error.detail || 'Failed to analyze floorplan');
    }
    return res.json();
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('Analysis timed out - please try again');
    }
    throw err;
  }
}

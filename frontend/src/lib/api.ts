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

export async function getOpportunities(): Promise<Opportunity[]> {
  const res = await fetch(`${API_URL}/api/opportunities?min_score=0`, {
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

export async function seedDemoData(): Promise<{ status: string; count: number }> {
  const res = await fetch(`${API_URL}/api/scraper/seed`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to seed demo data');
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

export interface ValuationResult {
  status: string;
  asking_price: number;
  num_units: number;
  estimated_unit_value: number | null;
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

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://titlesplit-api.onrender.com';

export interface Opportunity {
  id: string;
  title: string;
  address_line1: string;
  city: string;
  postcode: string;
  asking_price: number;
  estimated_units: number;
  tenure: string;
  opportunity_score: number;
  title_split_score: number;
  estimated_gross_uplift: number | null;
  status: string;
  source_url: string;
}

export async function getOpportunities(): Promise<Opportunity[]> {
  const res = await fetch(`${API_URL}/api/opportunities`, {
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

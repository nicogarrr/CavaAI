'use server';

import { revalidatePath } from 'next/cache';
import { researchRequest } from '@/lib/research/client';

export type DataSourceHealth = {
  layer: string; source: string | null; covered: number | null; total: number;
  coverage_pct: number | null; last_update: string | null; status: string;
  max_age_days: number | null; reason: string | null;
};
export type DataHealth = {
  as_of: string; total_companies: number; sources: DataSourceHealth[];
  connectors: { source: string; last_success: string | null; last_attempt: string | null; status: string; errors: number | null }[];
  coverage_basis: string; freshness_basis: string;
};
export type PublicShorts = {
  ticker: string; status: string; fetched_at: string | null; reason: string | null;
  data: null | {
    source: string; source_url: string; note: string; date?: string;
    short_volume?: number; total_volume?: number; short_volume_ratio?: number | null;
    public_total_percent?: number;
    positions?: { holder: string; percent: number; position_date: string }[];
  };
};
export async function getDataHealth(): Promise<DataHealth> {
  return researchRequest<DataHealth>('/api/data-health', { fast: true });
}
export async function getPublicShorts(ticker: string): Promise<PublicShorts> {
  return researchRequest<PublicShorts>(`/api/data-health/shorts/${encodeURIComponent(ticker)}`, { fast: true });
}
export async function refreshPublicShorts(ticker: string): Promise<void> {
  const result = await researchRequest<PublicShorts>(`/api/data-health/shorts/${encodeURIComponent(ticker)}/refresh`, { method: 'POST', timeoutMs: 65_000 });
  revalidatePath(`/research/${ticker}/shorts`);
  revalidatePath('/research/data-health');
  if (result.status === 'degraded') throw new Error(result.reason ?? 'La fuente no devolvió datos verificables.');
}

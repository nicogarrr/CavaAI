'use server';

import { researchRequest } from '@/lib/research/client';

export type AstOrbitSample = {
  epoch: string;
  sma_km: number;
  bstar: number | null;
  mean_motion_dot: number | null;
};
export type AstOrbitSignal = {
  status: string;
  delta_sma_km: number | null;
  hours: number | null;
};
export type AstOrbitObject = {
  norad_cat_id: number;
  object_name: string;
  epoch: string;
  sma_km: number | null;
  signal: AstOrbitSignal;
  history: AstOrbitSample[];
};
export type AstOrbitOverview = {
  status: 'disponible' | 'sin datos';
  source: string;
  source_url: string;
  cadence_hours: number;
  fetched_at: string | null;
  objects: AstOrbitObject[];
  usage_note: string;
};

export async function getAstOrbitOverview(): Promise<AstOrbitOverview> {
  return researchRequest<AstOrbitOverview>('/api/market/asts/orbits', { cache: 'no-store', fast: true });
}

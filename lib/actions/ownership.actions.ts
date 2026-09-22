'use server';

import { revalidatePath } from 'next/cache';

import { researchIdentityHeaders } from '@/lib/auth/research-identity';
import { ExternalAPIError } from '@/lib/types/errors';

const BACKEND_URL = process.env.FMP_BACKEND_URL ?? 'http://localhost:8000';

export type OwnershipManager = {
  cik: string;
  name: string;
};

export type OwnershipProvenance = {
  source: string;
  source_kind: string;
  source_url: string | null;
  fetched_at: string;
  coverage: string;
};

export type ManagerHoldingRow = {
  accession_number: string;
  is_amendment: boolean;
  name_of_issuer: string;
  title_of_class: string;
  cusip: string;
  value_usd_thousands: number | null;
  shares: number | null;
  share_type: string;
  put_call: string | null;
  investment_discretion: string;
  filing_url: string;
};

export type ManagerHoldings = {
  cik: string;
  manager?: string;
  status: 'ok' | 'unavailable';
  report_date?: string;
  coverage?: string;
  holdings: ManagerHoldingRow[];
  limitations?: string[];
  provenance?: OwnershipProvenance;
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const identity = await researchIdentityHeaders();
    const response = await fetch(`${BACKEND_URL}${path}`, {
      ...init,
      cache: 'no-store',
      headers: { ...identity, ...init?.headers },
    });
    if (!response.ok) throw new ExternalAPIError(`Research API ${response.status}: ${path}`, 'research-api');
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ExternalAPIError) throw error;
    throw new ExternalAPIError(`Research API request failed: ${path}`, 'research-api', error);
  }
}

export async function getOwnershipManagers(): Promise<{ managers: OwnershipManager[]; limitations: string[] }> {
  return requestJson('/api/ownership/managers');
}

export async function getManagerHoldings(cik: string): Promise<ManagerHoldings> {
  return requestJson(`/api/ownership/managers/${encodeURIComponent(cik)}/holdings`);
}

export async function syncOwnershipManagers(): Promise<void> {
  await requestJson('/api/ownership/managers/sync', { method: 'POST' });
  revalidatePath('/ownership');
}

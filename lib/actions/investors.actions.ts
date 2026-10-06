'use server';

import { normalizeResearchBody, researchIdentityHeaders } from '@/lib/auth/research-identity';
import { ExternalAPIError } from '@/lib/types/errors';

import type { ManagerChanges, OwnershipProvenance } from './ownership.actions';

const BACKEND_URL = process.env.FMP_BACKEND_URL ?? 'http://localhost:8000';

export type InvestorSummary = {
  slug: string;
  name: string;
  firm: string;
  kind: 'person' | 'firm' | 'company';
  cik: string | null;
  has_13f: boolean;
  /** 'partial' si el total guardado no cuadra con el declarado en el 13F; null sin datos. */
  coverage?: string | null;
  official_name: string | null;
  report_date: string | null;
  positions: number | null;
  value_usd_thousands: number | null;
  note: string | null;
};

export type InvestorHolding = {
  name_of_issuer: string;
  title_of_class: string;
  cusip: string;
  shares: number | null;
  value_usd_thousands: number | null;
  weight_pct: number | null;
  put_call: string | null;
  filing_url: string;
};

export type PublicFact = {
  label: string;
  value: string;
  as_of: string;
  source_url: string;
  kind: 'oficial' | 'inferido';
};

/** Ficha pública de gestores sin 13F: solo lo que publican ellos o un regulador, con fuente y fecha. */
export type PublicProfile = {
  vehicle: {
    name: string;
    type: string;
    regulator_id: string;
    manager_company: string;
    start_date: string;
    source_url: string;
  };
  facts: PublicFact[];
  letters: { title: string; date: string; url: string }[];
  meetings: { title: string; year: string; url: string }[];
  holdings: unknown[] | null;
  holdings_note: string;
  links: { label: string; url: string }[];
};

export type InvestorDetail = InvestorSummary & {
  public_profile?: PublicProfile | null;
  holdings: InvestorHolding[];
  limitations: string[];
  provenance?: OwnershipProvenance;
  changes?: ManagerChanges;
};

async function requestJson<T>(path: string): Promise<T> {
  try {
    const normalized = await normalizeResearchBody(null);
    const identity = await researchIdentityHeaders({
      method: 'GET',
      path,
      body: normalized.body ?? null,
    });
    const response = await fetch(`${BACKEND_URL}${path}`, {
      cache: 'no-store',
      headers: { ...identity },
    });
    if (response.status === 404) throw new ExternalAPIError(`Not found: ${path}`, 'research-api-404');
    if (!response.ok) throw new ExternalAPIError(`Research API ${response.status}: ${path}`, 'research-api');
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ExternalAPIError) throw error;
    throw new ExternalAPIError(`Research API request failed: ${path}`, 'research-api', error);
  }
}

export async function getInvestors(): Promise<{ investors: InvestorSummary[]; limitations: string[] }> {
  return requestJson('/api/investors');
}

/** Ficha de un inversor; `null` si el slug no existe (la página responde 404). */
export async function getInvestor(slug: string): Promise<InvestorDetail | null> {
  try {
    return await requestJson<InvestorDetail>(`/api/investors/${encodeURIComponent(slug)}`);
  } catch (error) {
    if (error instanceof ExternalAPIError && error.message.startsWith('Not found:')) return null;
    throw error;
  }
}

export type MostBoughtItem = {
  name_of_issuer: string;
  cusip: string;
  buyers_count: number;
  new_count: number;
  sellers_count: number;
  value_usd: number | null;
  buyers: { slug: string; name: string; change: 'new' | 'increased' }[];
};

export type MostBought = {
  status: 'ok' | 'sin_datos';
  managers_compared: number;
  managers_without_history: number;
  managers_partial?: number;
  report_dates: string[];
  items: MostBoughtItem[];
  limitations: string[];
};

export async function getMostBought(): Promise<MostBought> {
  return requestJson('/api/investors/most-bought');
}

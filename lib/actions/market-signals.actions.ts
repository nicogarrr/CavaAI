'use server';

import { revalidatePath } from 'next/cache';
import { researchIdentityHeaders } from '@/lib/auth/research-identity';

const BACKEND_URL = process.env.FMP_BACKEND_URL ?? 'http://localhost:8000';

export type InsiderSignal = {
  insider?: string;
  transaction_type?: string;
  transaction?: string;
  shares?: number | null;
  price?: number | null;
  filed_at?: string | null;
  [key: string]: unknown;
};

export type InsiderSignalsResult = {
  ticker: string;
  status: string;
  signals: InsiderSignal[];
  reason?: string | null;
};

export type EarningsCalendarEvent = {
  symbol?: string;
  name?: string;
  date?: string;
  time?: string | null;
  eps_estimate?: number | null;
  [key: string]: unknown;
};

export type EarningsCalendarResult = {
  status: string;
  count: number;
  events: EarningsCalendarEvent[];
  errors: string[];
};

const EMPTY_INSIDER: InsiderSignalsResult = { ticker: '', status: 'unavailable', signals: [] };
const EMPTY_CALENDAR: EarningsCalendarResult = { status: 'unavailable', count: 0, events: [], errors: [] };

async function safeGet<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${BACKEND_URL}${path}`, {
      cache: 'no-store',
      headers: await researchIdentityHeaders(),
    });
    if (!response.ok) return fallback;
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

/** Señales insider (Form 4). Nunca lanza: degrada a status unavailable. */
export async function getInsiderSignals(ticker: string): Promise<InsiderSignalsResult> {
  const normalized = ticker.toUpperCase();
  const fallback: InsiderSignalsResult = { ...EMPTY_INSIDER, ticker: normalized };
  const data = await safeGet<InsiderSignalsResult>(
    `/api/insider/signals?ticker=${encodeURIComponent(normalized)}&limit=10`,
    fallback,
  );
  if (!data || !Array.isArray(data.signals)) return fallback;
  return { ...fallback, ...data, signals: data.signals.slice(0, 10) };
}

/** Próximos earnings (7 días). Nunca lanza: degrada a status unavailable. */
export async function getEarningsCalendar(): Promise<EarningsCalendarResult> {
  const data = await safeGet<EarningsCalendarResult>('/api/calendar/earnings', EMPTY_CALENDAR);
  if (!data || !Array.isArray(data.events)) return EMPTY_CALENDAR;
  return { ...EMPTY_CALENDAR, ...data };
}

/** Debate bull/bear sobre la última tesis; persiste el veredicto en la tesis. */
export async function runResearchThesisDebate(ticker: string): Promise<{ verdict: string; persisted: boolean } | null> {
  const normalized = ticker.toUpperCase();
  try {
    const response = await fetch(`${BACKEND_URL}/api/thesis/${encodeURIComponent(normalized)}/debate`, {
      method: 'POST',
      headers: await researchIdentityHeaders(),
      cache: 'no-store',
    });
    if (!response.ok) return null;
    const payload = (await response.json()) as { verdict?: string; persisted?: boolean };
    revalidatePath(`/research/${normalized}`);
    return { verdict: payload.verdict ?? 'unknown', persisted: payload.persisted ?? false };
  } catch {
    return null;
  }
}

'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchRequest } from '@/lib/research/client';

export type InsiderSignal = Record<string, unknown>;

export interface InsiderSignalsResult extends Record<string, unknown> {
    ticker: string;
    cik?: string | null;
    status: string;
    filings_scanned?: number;
    buy_count?: number;
    signals: InsiderSignal[];
    reason?: string;
    filing_errors?: string[];
    notification?: Record<string, unknown>;
}

export interface InsiderSignalsOptions {
    limit?: number;
    notify?: boolean;
}

/** GET /api/insider/signals — señales cluster_buy / c_suite_buy / big_buy (Form 4, SEC EDGAR) */
export async function getInsiderSignals(
    ticker: string,
    options?: InsiderSignalsOptions,
): Promise<InsiderSignalsResult> {
    await requireAuthenticatedUser();
    const clean = ticker.trim().toUpperCase();
    const params = new URLSearchParams({ ticker: clean });
    if (options?.limit !== undefined) params.set('limit', String(options.limit));
    if (options?.notify) params.set('notify', 'true');
    return researchRequest<InsiderSignalsResult>(`/api/insider/signals?${params.toString()}`);
}

export interface InsiderFilingTransaction {
    insider?: string | null;
    role?: string | null;
    officer_title?: string | null;
    code?: string | null;
    shares?: number | null;
    price?: number | null;
    value?: number | null;
    tx_date?: string | null;
    source_url?: string | null;
}

export interface InsiderFilingEntry {
    accession_number: string;
    form: string;
    is_amendment: boolean;
    filing_date?: string | null;
    report_date?: string | null;
    source_url?: string | null;
    transaction_count: number;
    transactions: InsiderFilingTransaction[];
}

export interface InsiderFilingsResult {
    ticker: string;
    status: string;
    reason?: string;
    count: number;
    filings: InsiderFilingEntry[];
}

/** GET /api/insider/filings — filings Form 4/4-A persistidos (lectura durable). */
export async function getInsiderFilings(
    ticker: string,
    limit = 20,
): Promise<InsiderFilingsResult> {
    await requireAuthenticatedUser();
    const clean = ticker.trim().toUpperCase();
    const params = new URLSearchParams({ ticker: clean, limit: String(limit) });
    return researchRequest<InsiderFilingsResult>(`/api/insider/filings?${params.toString()}`);
}

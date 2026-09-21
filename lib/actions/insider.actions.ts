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

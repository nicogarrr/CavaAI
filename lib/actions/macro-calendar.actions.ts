'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchRequest } from '@/lib/research/client';

export type MacroEvent = {
    kind: string;
    date: string;
    start_date: string;
    time_et: string | null;
    title: string;
    detail: string | null;
    source: string;
    source_url: string;
    label: 'OFICIAL';
};

export type MacroSource = {
    name: string;
    url: string;
    status: 'ready' | 'partial' | 'unavailable';
    fetched_at: string;
    covered_until: string | null;
};

export type MacroEventsResult = {
    status: 'ready' | 'partial' | 'unavailable';
    from: string;
    to: string;
    total: number;
    page: number;
    page_size: number;
    events: MacroEvent[];
    sources: MacroSource[];
};

export type EightKItem = {
    code: string;
    title: string;
    official_title: string | null;
    excerpts: { text: string; chunk_id: number }[];
};

export type EightKEntry = {
    document_id: number;
    ticker: string;
    company: string;
    filed_at: string | null;
    source: 'SEC';
    source_url: string;
    label: 'OFICIAL';
    matching: string[];
    status: 'ready' | 'insufficient_data';
    reason?: string;
    items: EightKItem[];
};

export type EightKDigest = {
    status: 'ready' | 'insufficient_data';
    reason: string | null;
    page: number;
    page_size: number;
    total: number;
    scanned: number;
    items: EightKEntry[];
};

/** GET /api/macro-calendar/events: FOMC y publicaciones BLS (fuentes oficiales). */
export async function getMacroEvents(page = 1): Promise<MacroEventsResult> {
    await requireAuthenticatedUser();
    return researchRequest<MacroEventsResult>(
        `/api/macro-calendar/events?page=${page}&page_size=10`,
    );
}

/** GET /api/macro-calendar/8k: 8-K recientes de cartera y watchlist. */
export async function getEightKDigest(page = 1): Promise<EightKDigest> {
    await requireAuthenticatedUser();
    return researchRequest<EightKDigest>(`/api/macro-calendar/8k?page=${page}&page_size=5`);
}

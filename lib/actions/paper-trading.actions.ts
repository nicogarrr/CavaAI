'use server';

import { researchRequest } from '@/lib/research/client';
import { AppError } from '@/lib/types/errors';

export interface PaperTradeView {
    id: number; ticker: string; direction: 'long' | 'short'; horizon: 'short' | 'five_years';
    thesis: string; conviction: string; proposed_entry: string; stop: string; target: string;
    inference_basis: string; status: string; currency: string | null; created_at: string;
    entry_price: string | null; exit_price: string | null; mark_price: string | null;
    mark_at: string | null; entry_at: string | null; exit_at: string | null;
    realized_pnl: string | null; unrealized_pnl: string | null; close_reason: string | null;
}
export interface PaperScore {
    groups: Array<{ horizon: string; currency: string; proposals: number; closed: number;
        open: number; wins: number; losses: number; flat: number; hit_rate: number | null;
        realized_pnl: string | null; unrealized_pnl: string | null; missing_marks: number }>;
}
export type PaperState = { trades: PaperTradeView[]; score: PaperScore; error?: string };

export async function getPaperTrading(): Promise<PaperState> {
    try {
        const [trades, score] = await Promise.all([
            researchRequest<PaperTradeView[]>('/api/paper-trading/proposals'),
            researchRequest<PaperScore>('/api/paper-trading/scoreboard'),
        ]);
        return { trades, score };
    } catch (error) {
        if (error instanceof AppError && ['EXTERNAL_API_ERROR', 'RESEARCH_API_ERROR'].includes(error.code) && ![401, 403].includes(error.statusCode ?? 0)) {
            return { trades: [], score: { groups: [] }, error: 'No se pudo cargar la cartera simulada.' };
        }
        throw error;
    }
}

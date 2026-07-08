'use server';

import { getPortfolioSummary } from './portfolio.actions';

const BACKEND_URL = process.env.FMP_BACKEND_URL ?? 'http://localhost:8000';

export type MonteCarloModelResult = {
    name: string;
    label: string;
    category: string;
    bust_probability: number | null;
    goal_probability: number | null;
    percentile_5: number | null;
    percentile_25: number | null;
    median: number | null;
    percentile_75: number | null;
    percentile_95: number | null;
    mean: number | null;
    std: number | null;
};

export type MonteCarloResult = {
    symbols: string[];
    horizon_days: number;
    simulations: number;
    bust_threshold: number;
    goal_threshold: number;
    models: Record<string, MonteCarloModelResult>;
    summary: {
        cross_model_median_return: number | null;
        models_run: number;
        conservative_envelope: number | null;
    };
};

export async function generateRiskAnalysis(
    userId: string,
    horizon: number = 252,
    sims: number = 500,
): Promise<MonteCarloResult | { error: string }> {
    try {
        const summary = await getPortfolioSummary(userId);

        if (summary.holdings.length === 0) {
            return { error: 'No holdings in portfolio' };
        }

        const symbols = summary.holdings.map(h => h.symbol);
        const totalValue = summary.totalValue;
        const weights = totalValue > 0
            ? summary.holdings.map(h => h.value / totalValue)
            : undefined;

        const res = await fetch(`${BACKEND_URL}/analytics/montecarlo`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbols,
                weights,
                period: '3y',
                horizon,
                sims,
                bust: -0.5,
                goal: 0.5,
                models: ['gbm', 'bootstrap', 'block_bootstrap', 'garch'],
            }),
        });

        if (!res.ok) {
            const err = await res.text();
            console.error('Monte Carlo endpoint error:', res.status, err);
            return { error: `Backend error ${res.status}` };
        }

        return await res.json() as MonteCarloResult;
    } catch (error) {
        console.error('Error generating risk analysis:', error);
        return { error: String(error) };
    }
}

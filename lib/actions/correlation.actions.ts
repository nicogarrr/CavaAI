'use server';

import { cache } from 'react';

const BACKEND_URL = process.env.FMP_BACKEND_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CorrelationPair = {
    symbol_a: string;
    symbol_b: string;
    correlation: number | null;
    abs_correlation: number | null;
    level: 'high' | 'medium' | 'low';
};

export type CorrelationMatrixResult = {
    symbols: string[];
    trading_days: number;
    period: string;
    method: string;
    matrix: Record<string, Record<string, number | null>>;
    pairs: CorrelationPair[];
};

// Keep old type alias for components that haven't migrated yet
export type CorrelationData = {
    symbol1: string;
    symbol2: string;
    correlation: number;
    period: string;
    significance: 'high' | 'medium' | 'low';
};

export type DiversificationAnalysis = {
    sectorAllocation: Array<{ sector: string; percentage: number; count: number }>;
    regionAllocation: Array<{ region: string; percentage: number; count: number }>;
    concentrationRisk: {
        herfindahlIndex: number;
        maxSingleHolding: number;
        top5Concentration: number;
        riskLevel: 'low' | 'medium' | 'high';
    };
    correlationInsights: Array<{
        type: 'high_correlation' | 'low_correlation' | 'negative_correlation';
        pairs: Array<{ symbol1: string; symbol2: string; correlation: number }>;
        recommendation: string;
    }>;
};

// ---------------------------------------------------------------------------
// Core: backend-powered correlation (Python, aligned inner join)
// ---------------------------------------------------------------------------

export const calculateCorrelationMatrix = cache(async (
    symbols: string[],
    period: string = '1y',
    method: 'pearson' | 'spearman' = 'pearson',
): Promise<CorrelationMatrixResult | null> => {
    if (symbols.length < 2) return null;

    try {
        const res = await fetch(`${BACKEND_URL}/analytics/correlation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbols: symbols.map(s => s.toUpperCase()), period, method }),
            next: { revalidate: 3600 },
        });

        if (!res.ok) {
            console.error('Correlation endpoint error:', res.status);
            return null;
        }

        return await res.json() as CorrelationMatrixResult;
    } catch (error) {
        console.error('Error fetching correlation matrix:', error);
        return null;
    }
});

// ---------------------------------------------------------------------------
// Backward-compat adapter: returns CorrelationData[] for existing components
// ---------------------------------------------------------------------------

export async function getCorrelationPairs(
    symbols: string[],
    period: string = '1y',
): Promise<CorrelationData[]> {
    const result = await calculateCorrelationMatrix(symbols, period);
    if (!result) return [];

    return result.pairs.map(p => ({
        symbol1: p.symbol_a,
        symbol2: p.symbol_b,
        correlation: p.correlation ?? 0,
        period: result.period,
        significance: p.level,
    }));
}

// ---------------------------------------------------------------------------
// Diversification analysis (concentration + correlation insights)
// ---------------------------------------------------------------------------

export const analyzeDiversification = cache(async (
    positions: Array<{
        symbol: string;
        percentage: number;
        sector?: string;
        region?: string;
    }>,
): Promise<DiversificationAnalysis> => {
    // Concentration metrics (no external call needed)
    const sectorMap = new Map<string, { percentage: number; count: number }>();
    const regionMap = new Map<string, { percentage: number; count: number }>();

    for (const pos of positions) {
        const sector = pos.sector ?? 'Unknown';
        const region = pos.region ?? 'Unknown';

        const s = sectorMap.get(sector) ?? { percentage: 0, count: 0 };
        s.percentage += pos.percentage; s.count += 1;
        sectorMap.set(sector, s);

        const r = regionMap.get(region) ?? { percentage: 0, count: 0 };
        r.percentage += pos.percentage; r.count += 1;
        regionMap.set(region, r);
    }

    const sectorAllocation = Array.from(sectorMap.entries())
        .map(([sector, d]) => ({ sector, percentage: d.percentage, count: d.count }))
        .sort((a, b) => b.percentage - a.percentage);

    const regionAllocation = Array.from(regionMap.entries())
        .map(([region, d]) => ({ region, percentage: d.percentage, count: d.count }))
        .sort((a, b) => b.percentage - a.percentage);

    const percentages = positions.map(p => p.percentage);
    const herfindahlIndex = percentages.reduce((s, p) => s + p * p, 0);
    const maxSingleHolding = percentages.length ? Math.max(...percentages) : 0;
    const top5Concentration = [...percentages].sort((a, b) => b - a).slice(0, 5).reduce((s, p) => s + p, 0);

    let riskLevel: 'low' | 'medium' | 'high' = 'low';
    if (herfindahlIndex > 0.25 || maxSingleHolding > 0.3 || top5Concentration > 0.7) riskLevel = 'high';
    else if (herfindahlIndex > 0.15 || maxSingleHolding > 0.2 || top5Concentration > 0.5) riskLevel = 'medium';

    // Correlation insights via backend
    const symbols = positions.map(p => p.symbol);
    const corrResult = await calculateCorrelationMatrix(symbols, '3m');
    const pairs = corrResult?.pairs ?? [];

    const highCorr = pairs.filter(p => p.abs_correlation != null && p.abs_correlation > 0.7);
    const lowCorr = pairs.filter(p => p.abs_correlation != null && p.abs_correlation < 0.3);
    const negCorr = pairs.filter(p => p.correlation != null && p.correlation < -0.3);

    const correlationInsights: DiversificationAnalysis['correlationInsights'] = [];

    if (highCorr.length > 0) {
        correlationInsights.push({
            type: 'high_correlation',
            pairs: highCorr.map(p => ({ symbol1: p.symbol_a, symbol2: p.symbol_b, correlation: p.correlation ?? 0 })),
            recommendation: 'Considera reducir la exposición a activos altamente correlacionados para mejorar la diversificación.',
        });
    }
    if (lowCorr.length > 0) {
        correlationInsights.push({
            type: 'low_correlation',
            pairs: lowCorr.slice(0, 3).map(p => ({ symbol1: p.symbol_a, symbol2: p.symbol_b, correlation: p.correlation ?? 0 })),
            recommendation: 'Excelente diversificación: estos activos tienen baja correlación.',
        });
    }
    if (negCorr.length > 0) {
        correlationInsights.push({
            type: 'negative_correlation',
            pairs: negCorr.map(p => ({ symbol1: p.symbol_a, symbol2: p.symbol_b, correlation: p.correlation ?? 0 })),
            recommendation: 'Activos con correlación negativa proporcionan excelente diversificación.',
        });
    }

    return { sectorAllocation, regionAllocation, concentrationRisk: { herfindahlIndex, maxSingleHolding, top5Concentration, riskLevel }, correlationInsights };
});

// ---------------------------------------------------------------------------
// Rebalancing recommendations
// ---------------------------------------------------------------------------

export const getRebalancingRecommendations = cache(async (
    positions: Array<{ symbol: string; percentage: number; sector?: string }>,
): Promise<Array<{ type: 'reduce' | 'increase' | 'add' | 'remove'; symbol: string; currentWeight: number; recommendedWeight: number; reason: string }>> => {
    const symbols = positions.map(p => p.symbol);
    const corrResult = await calculateCorrelationMatrix(symbols, '3m');
    const pairs = corrResult?.pairs ?? [];

    const recommendations: ReturnType<typeof getRebalancingRecommendations> extends Promise<infer T> ? T : never[] = [];

    // High-correlation pairs (> 0.8)
    for (const pair of pairs.filter(p => p.abs_correlation != null && p.abs_correlation > 0.8)) {
        const pos1 = positions.find(p => p.symbol === pair.symbol_a);
        const pos2 = positions.find(p => p.symbol === pair.symbol_b);
        if (!pos1 || !pos2) continue;

        const smaller = pos1.percentage <= pos2.percentage ? pos1 : pos2;
        const larger = pos1.percentage > pos2.percentage ? pos1 : pos2;

        recommendations.push({
            type: 'reduce',
            symbol: smaller.symbol,
            currentWeight: smaller.percentage,
            recommendedWeight: smaller.percentage * 0.5,
            reason: `Alta correlación (${((pair.abs_correlation ?? 0) * 100).toFixed(1)}%) con ${larger.symbol}`,
        });
    }

    // Overweight sectors (> 40%)
    const sectorWeights = new Map<string, number>();
    for (const pos of positions) {
        const sector = pos.sector ?? 'Unknown';
        sectorWeights.set(sector, (sectorWeights.get(sector) ?? 0) + pos.percentage);
    }
    for (const [sector, weight] of sectorWeights.entries()) {
        if (weight > 0.4) {
            for (const pos of positions.filter(p => (p.sector ?? 'Unknown') === sector)) {
                recommendations.push({
                    type: 'reduce',
                    symbol: pos.symbol,
                    currentWeight: pos.percentage,
                    recommendedWeight: pos.percentage * 0.8,
                    reason: `Sobreponderación en sector ${sector} (${(weight * 100).toFixed(1)}%)`,
                });
            }
        }
    }

    return recommendations;
});

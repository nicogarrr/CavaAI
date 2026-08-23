'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { getCandles } from '@/lib/actions/finnhub.actions';
import { generateProPicksForStrategy, getAvailableStrategies } from '@/lib/actions/proPicks.actions';
import { simulateStrategy, type BacktestResult } from '@/lib/utils/backtesting';

export interface StrategyBacktestOutput {
    strategyId: string;
    strategyName: string;
    result: BacktestResult;
}

/**
 * Genera picks para una estrategia ProPicks y simula un backtest
 * con velas históricas reales (período de tenencia de 30 sesiones).
 */
export async function runStrategyBacktest(
    strategyId: string,
): Promise<StrategyBacktestOutput | { error: string }> {
    try {
        await requireAuthenticatedUser();

        const strategies = await getAvailableStrategies();
        const strategy = strategies.find((item) => item.id === strategyId) ?? strategies[0];
        if (!strategy) {
            return { error: 'No hay estrategias disponibles' };
        }

        // Evaluar el universo para esta estrategia (límite pequeño para mantener el backtest ágil)
        const picks = (await generateProPicksForStrategy(strategy.id, 6)).filter((pick) => pick.score >= 70);
        if (picks.length === 0) {
            return { error: 'No se pudieron generar picks para esta estrategia' };
        }

        const to = Math.floor(Date.now() / 1000);
        const from = to - 240 * 24 * 60 * 60; // ventana de ~8 meses
        const historicalPrices: Record<string, Array<{ date: string; price: number }>> = {};
        const entries: Array<{ symbol: string; entryDate: string; entryPrice: number }> = [];

        for (const pick of picks.slice(0, 5)) {
            const candles = await getCandles(pick.symbol, from, to, 'D', 3600).catch(() => null);
            if (candles?.s !== 'ok' || candles.c.length < 90) continue;

            historicalPrices[pick.symbol] = candles.t.map((timestamp, index) => ({
                date: new Date(timestamp * 1000).toISOString(),
                price: candles.c[index],
            }));

            // Entrada ~60 sesiones atrás para dejar margen de salida en el backtest
            const entryIndex = candles.c.length - 1 - 60;
            entries.push({
                symbol: pick.symbol,
                entryDate: new Date(candles.t[entryIndex] * 1000).toISOString(),
                entryPrice: candles.c[entryIndex],
            });
        }

        const spy = await getCandles('SPY', from, to, 'D', 3600).catch(() => null);
        const benchmarkPrices = spy?.s === 'ok'
            ? spy.t.map((timestamp, index) => ({
                  date: new Date(timestamp * 1000).toISOString(),
                  price: spy.c[index],
              }))
            : [];

        if (entries.length === 0) {
            return { error: 'No hay datos de mercado suficientes para el backtest' };
        }

        const result = simulateStrategy(strategy.id, strategy.name, entries, historicalPrices, benchmarkPrices, 30);
        return { strategyId: strategy.id, strategyName: strategy.name, result };
    } catch (error) {
        console.error('Error ejecutando backtest de estrategia:', error);
        return { error: error instanceof Error ? error.message : String(error) };
    }
}
'use server';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { getResearchCompanyBasics } from '@/lib/actions/market-workspace.actions';
import { getCandles } from '@/lib/actions/finnhub.actions';
import { quoteSymbolFor } from '@/lib/market/quote-symbol';
import { chartRequestWindow, intradayWindow, isChartRange } from '@/lib/market/chart-ranges';
import { e2eMarketFixture, isE2EMarketFixtureEnabled } from '@/lib/e2e-market-fixture';
import { cleanBars, hasOHLC, type TechnicalBar } from '@/lib/market/technical';
export type CompanyChartBar = TechnicalBar & { timestamp?: number };
export type CompanyChartHistory = { bars: CompanyChartBar[]; source: string | null; resolution: 'D' | '60' };

export async function getCompanyChartHistory(ticker: string, range: string): Promise<CompanyChartHistory> {
    await requireAuthenticatedUser();
    if (!isChartRange(range) || !/^[A-Z0-9.^-]{1,24}$/.test(ticker)) throw new Error('Rango o empresa no válido');
    if (isE2EMarketFixtureEnabled(process.env, ticker)) {
        const seed = e2eMarketFixture(ticker);
        if (range === '1D' || range === '5D') {
            const bars = Array.from({ length: 35 }, (_, i) => ({ date: new Date(Date.UTC(2026, 8, 5 + Math.floor(i / 7))).toISOString().slice(0, 10), timestamp: Date.UTC(2026, 8, 5 + Math.floor(i / 7), 13 + i % 7) / 1000, open: 330 + i, high: 333 + i, low: 329 + i, close: 331 + i, volume: 1000 + i }));
            return { bars: intradayWindow(bars, range), source: 'Fixture local', resolution: '60' };
        }
        return { bars: seed.history, source: 'Fixture local', resolution: 'D' };
    }
    const window = chartRequestWindow(range, Date.now() / 1000);
    const empty: CompanyChartHistory = { bars: [], source: null, resolution: window.resolution };
    const company = await getResearchCompanyBasics(ticker);
    const symbol = quoteSymbolFor(company, ticker);
    if (!symbol) return empty; // Never read a same-ticker listing from the wrong exchange.
    const candles = await getCandles(symbol, window.from, window.to, window.resolution, 900);
    if (candles.s !== 'ok') return empty;
    const byTimestamp = new Map<number, CompanyChartBar>();
    candles.t.forEach((timestamp, index) => {
        const close = candles.c[index];
        if (!Number.isFinite(timestamp) || timestamp < window.from || timestamp > window.to || !Number.isFinite(close) || close <= 0) return;
        const raw = { date: new Date(timestamp * 1000).toISOString().slice(0, 10), close, open: candles.o?.[index] ?? null, high: candles.h?.[index] ?? null, low: candles.l?.[index] ?? null, volume: candles.v?.[index] ?? null };
        // Bad OHLC does not destroy a genuine close, but cannot drive indicators.
        const bar = hasOHLC(raw) ? raw : { ...raw, open: null, high: null, low: null };
        byTimestamp.set(timestamp, { ...bar, ...(window.resolution === '60' ? { timestamp } : {}) });
    });
    const bars = [...byTimestamp.entries()].sort(([a], [b]) => a - b).map(([, bar]) => bar);
    return { bars: range === '1D' || range === '5D' ? intradayWindow(bars, range) : cleanBars(bars), source: candles.source ?? null, resolution: window.resolution };
}

// @ts-expect-error Node regression harness requires an explicit extension.
import { cleanBars, hasOHLC, type TechnicalBar } from './technical.ts';
export type CompanyChartBar = TechnicalBar & { timestamp?: number };
export type CandlePayload = { s: string; c: number[]; t: number[]; o: (number | null)[]; h: (number | null)[]; l: (number | null)[]; v: (number | null)[] };
/** Real boundary used by the server action. Missing OHLC never becomes a candle. */
export function normalizeChartCandles(candles: CandlePayload, window: { from: number; to: number; resolution: 'D' | '60' }): CompanyChartBar[] {
    if (candles.s !== 'ok') return [];
    const byTimestamp = new Map<number, CompanyChartBar>();
    candles.t.forEach((timestamp, index) => {
        const close = candles.c[index];
        if (!Number.isFinite(timestamp) || timestamp < window.from || timestamp > window.to || !Number.isFinite(close) || close <= 0) return;
        const epoch = timestamp * 1000;
        if (!Number.isFinite(new Date(epoch).getTime())) return;
        const raw = { date: new Date(epoch).toISOString().slice(0, 10), close, open: candles.o?.[index] ?? null, high: candles.h?.[index] ?? null, low: candles.l?.[index] ?? null, volume: candles.v?.[index] ?? null };
        const bar = hasOHLC(raw) ? raw : { ...raw, open: null, high: null, low: null };
        byTimestamp.set(timestamp, { ...bar, ...(window.resolution === '60' ? { timestamp } : {}) });
    });
    const bars = [...byTimestamp.entries()].sort(([a], [b]) => a - b).map(([, bar]) => bar);
    return window.resolution === 'D' ? cleanBars(bars) : bars;
}

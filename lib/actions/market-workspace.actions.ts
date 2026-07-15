'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { getCandles, getProfile, getStockQuote } from '@/lib/actions/finnhub.actions';

export type CompanyMarketSnapshot = {
    ticker: string;
    name: string;
    exchange: string | null;
    currency: string | null;
    quote: {
        price: number | null;
        change: number | null;
        changePercent: number | null;
        open: number | null;
        high: number | null;
        low: number | null;
        previousClose: number | null;
    };
    history: Array<{ date: string; close: number; volume: number | null }>;
    status: 'available' | 'partial' | 'unavailable';
};

export async function getCompanyMarketSnapshot(ticker: string): Promise<CompanyMarketSnapshot> {
    await requireAuthenticatedUser();
    const normalized = ticker.trim().toUpperCase();
    if (process.env.E2E_AUTH_BYPASS === '1' && process.env.NODE_ENV !== 'production') {
        return {
            ticker: normalized,
            name: normalized,
            exchange: null,
            currency: null,
            quote: { price: null, change: null, changePercent: null, open: null, high: null, low: null, previousClose: null },
            history: [],
            status: 'unavailable',
        };
    }
    const to = Math.floor(Date.now() / 1000);
    const from = to - 366 * 24 * 60 * 60;
    const [profile, quote, candles] = await Promise.all([
        getProfile(normalized),
        getStockQuote(normalized),
        getCandles(normalized, from, to, 'D', 900),
    ]);
    const history = candles.s === 'ok'
        ? candles.t.map((timestamp, index) => ({
            date: new Date(timestamp * 1000).toISOString().slice(0, 10),
            close: candles.c[index],
            volume: candles.v[index] ?? null,
        })).filter((point) => Number.isFinite(point.close))
        : [];
    const price = quote?.c && quote.c > 0 ? quote.c : history.at(-1)?.close ?? null;
    return {
        ticker: normalized,
        name: profile?.name || normalized,
        exchange: profile?.exchange || null,
        currency: profile?.currency || null,
        quote: {
            price,
            change: quote?.d ?? null,
            changePercent: quote?.dp ?? null,
            open: quote?.o ?? null,
            high: quote?.h ?? null,
            low: quote?.l ?? null,
            previousClose: quote?.pc ?? null,
        },
        history,
        status: price != null && history.length ? 'available' : price != null ? 'partial' : 'unavailable',
    };
}

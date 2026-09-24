'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchIdentityHeaders } from '@/lib/auth/research-identity';
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


type ResearchCompanyBasics = { name?: string; exchange?: string; currency?: string };

// Finnhub profile2 no siempre cubre mercados no-US; la ficha research sí
// tiene la compañía (resuelve sufijos, SAN.MC -> SAN) con nombre/bolsa/moneda.
async function getResearchCompanyBasics(ticker: string): Promise<ResearchCompanyBasics | null> {
    const backendUrl = process.env.FMP_BACKEND_URL;
    if (!backendUrl) return null;
    try {
        const path = `/api/companies/${encodeURIComponent(ticker)}`;
        const response = await fetch(`${backendUrl}${path}`, {
            headers: await researchIdentityHeaders({ method: 'GET', path }),
            signal: AbortSignal.timeout(4000),
        });
        if (!response.ok) return null;
        const data = await response.json();
        if (!data || typeof data !== 'object') return null;
        return data as ResearchCompanyBasics;
    } catch {
        return null;
    }
}

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
    const [profile, quote, candles, researchCompany] = await Promise.all([
        getProfile(normalized),
        getStockQuote(normalized),
        getCandles(normalized, from, to, 'D', 900),
        getResearchCompanyBasics(normalized),
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
        name: profile?.name || researchCompany?.name || normalized,
        exchange: profile?.exchange || researchCompany?.exchange || null,
        currency: profile?.currency || researchCompany?.currency || null,
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

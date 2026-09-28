'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchIdentityHeaders } from '@/lib/auth/research-identity';
import { getCandles, getProfile, getStockQuote } from '@/lib/actions/finnhub.actions';
import { marketHistoryStatus } from '@/lib/market/history-status';
import { quoteSymbolFor } from '@/lib/market/quote-symbol';
import { e2eMarketFixture, isE2EMarketFixtureEnabled } from '@/lib/e2e-market-fixture';

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
        // Fecha del dato mostrado como precio: cotización en vivo -> null;
        // fallback al último cierre de vela -> la fecha de esa vela, para
        // que la cabecera la rotule y no parezca precio actual.
        priceAsOf: string | null;
    };
    history: Array<{ date: string; close: number; volume: number | null }>;
    status: 'available' | 'partial' | 'unavailable';
};


type ResearchCompanyBasics = { name?: string; exchange?: string; currency?: string };

// Finnhub profile2 no siempre cubre mercados no-US; la ficha research sí
// tiene la compañía (resuelve sufijos, SAN.MC -> SAN) con nombre/bolsa/moneda.
export async function getResearchCompanyBasics(ticker: string): Promise<ResearchCompanyBasics | null> {
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
    if (isE2EMarketFixtureEnabled(process.env, normalized)) {
        return e2eMarketFixture(normalized);
    }
    const to = Math.floor(Date.now() / 1000);
    const from = to - 366 * 24 * 60 * 60;
    // El master primero: su bolsa/divisa deciden el símbolo de cotización.
    const researchCompany = await getResearchCompanyBasics(normalized);
    const quoteSymbol = quoteSymbolFor(researchCompany, normalized);
    if (!quoteSymbol) {
        // Sin identidad de listado verificada (master inaccesible) o sin
        // correspondencia de bolsa validada: cotización NO disponible. Un
        // fallo transitorio del master nunca abre la vía del ticker desnudo,
        // que puede devolver el precio de otro emisor (ALM->Almonty).
        return {
            ticker: normalized,
            name: researchCompany?.name || normalized,
            exchange: researchCompany?.exchange || null,
            currency: researchCompany?.currency || null,
            quote: { price: null, change: null, changePercent: null, open: null, high: null, low: null, previousClose: null, priceAsOf: null },
            history: [],
            status: 'unavailable',
        };
    }
    const [profile, quote, candles] = await Promise.all([
        getProfile(quoteSymbol),
        getStockQuote(quoteSymbol),
        getCandles(quoteSymbol, from, to, 'D', 900),
    ]);
    const history = candles.s === 'ok'
        ? candles.t.map((timestamp, index) => ({
            date: new Date(timestamp * 1000).toISOString().slice(0, 10),
            close: candles.c[index],
            volume: candles.v[index] ?? null,
        })).filter((point) => Number.isFinite(point.close))
        : [];
    const livePrice = quote?.c;
    const quoteLive = typeof livePrice === 'number' && livePrice > 0;
    const lastClose = history.at(-1) ?? null;
    const price = quoteLive ? livePrice : lastClose?.close ?? null;
    // Fallback a cierre de vela: la variación del proveedor describe la
    // cotización en vivo, no ese cierre; se omite para no mezclar fuentes.
    const change = quoteLive ? quote?.d ?? null : null;
    const changePercent = quoteLive ? quote?.dp ?? null : null;
    const priceAsOf = quoteLive ? null : lastClose?.date ?? null;
    return {
        ticker: normalized,
        // La identidad la pone el master (curado); el perfil del proveedor
        // solo rellena huecos - nunca puede rebautizar la ficha con el
        // gemelo americano del ticker.
        name: researchCompany?.name || profile?.name || normalized,
        exchange: researchCompany?.exchange || profile?.exchange || null,
        currency: researchCompany?.currency || profile?.currency || null,
        quote: {
            price,
            change,
            changePercent,
            open: quote?.o ?? null,
            high: quote?.h ?? null,
            low: quote?.l ?? null,
            previousClose: quote?.pc ?? null,
            priceAsOf,
        },
        history,
        // La insignia del historial describe la serie (F161): sin velas es
        // «no disponible» aunque la cotización puntual haya cargado.
        status: marketHistoryStatus(history.length),
    };
}

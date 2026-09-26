'use server';

import { getDateRange, validateArticle, formatArticle } from '@/lib/utils';
import { POPULAR_STOCK_SYMBOLS } from '@/lib/constants';
import type { PopularStocksResult } from '@/lib/popular-stocks-loader';
import { cache } from 'react';
import { cachedFetch } from '@/lib/cache/memoryTTL';

import { env } from '@/lib/env';
import { TIMEOUTS } from '@/lib/constants';
import { ExternalAPIError, RateLimitError, toAppError } from '@/lib/types/errors';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchIdentityHeaders } from '@/lib/auth/research-identity';
// fetchJSON vive fuera del 'use server' a proposito: exportarlo aqui lo
// convertiria en un Server Action invocable por HTTP con una URL arbitraria
// (SSRF). Ver lib/upstream/finnhub.ts.
import { fetchJSON, redactUrl } from '@/lib/upstream/finnhub';

const FINNHUB_BASE_URL = env.FINNHUB_BASE_URL;

export type FinnhubCandles = { s: 'ok' | 'no_data'; c: number[]; t: number[]; o: number[]; h: number[]; l: number[]; v: number[] };

export async function getCandles(symbol: string, from: number, to: number, resolution: 'D' | 'W' | 'M' | '60' = 'D', revalidateSeconds = 1800): Promise<FinnhubCandles> {
    await requireAuthenticatedUser();
    const noData: FinnhubCandles = { s: 'no_data', c: [], t: [], o: [], h: [], l: [], v: [] };
    const token = env.FINNHUB_API_KEY;
    if (token) {
        const url = `${FINNHUB_BASE_URL}/stock/candle?symbol=${encodeURIComponent(symbol)}&resolution=${resolution}&from=${from}&to=${to}&token=${token}`;
        try {
            const result = await fetchJSON<FinnhubCandles>(url, revalidateSeconds);
            // fetchJSON puede retornar array vacío en caso de error, verificar si es un objeto válido
            if (!Array.isArray(result) && result && typeof result === 'object' && result.s === 'ok' && result.c?.length) {
                return result;
            }
        } catch {
            // Si el plan no permite el recurso (403) u otro error, seguimos al fallback
        }
    }
    // Fallback al backend (Yahoo chart API): Finnhub free no sirve velas de
    // mercados no-US (IBEX .MC...). Sin fallback el gráfico de la ficha sale vacío.
    const backendUrl = process.env.FMP_BACKEND_URL;
    if (backendUrl) {
        try {
            const path = `/api/market/candles/${encodeURIComponent(symbol)}`;
            const identityHeaders = await researchIdentityHeaders({ method: 'GET', path });
            const response = await fetch(`${backendUrl}${path}?from=${from}&to=${to}&resolution=${resolution}`, {
                headers: identityHeaders,
                signal: AbortSignal.timeout(8000),
            });
            if (response.ok) {
                const data = await response.json();
                if (data && data.s === 'ok' && Array.isArray(data.c) && data.c.length) {
                    return data;
                }
            }
        } catch {
            // Backend caído o sin datos: estado vacío honesto
        }
    }
    return noData;
}

export type FinnhubProfile2 = { ticker?: string; name?: string; exchange?: string; currency?: string; country?: string; ipo?: string; logo?: string; weburl?: string };
export const getProfile = cache(async (symbol: string): Promise<FinnhubProfile2 | null> => {
    await requireAuthenticatedUser();
    // Caché corta en memoria (60s) para llamadas en bucle (watchlist,
    // screener, market snapshot): el fetch interno ya revalida cada hora,
    // esta capa evita repetir el round-trip dentro de la ventana.
    return cachedFetch<FinnhubProfile2 | null>(
        `finnhub:profile:${symbol.trim().toUpperCase()}`,
        () => fetchProfile(symbol),
        60,
    );
});

async function fetchProfile(symbol: string): Promise<FinnhubProfile2 | null> {
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) return null;
        const url = `${FINNHUB_BASE_URL}/stock/profile2?symbol=${encodeURIComponent(symbol)}&token=${token}`;
        const result = await fetchJSON<FinnhubProfile2>(url, 3600);
        // fetchJSON puede retornar array vacío en caso de error, verificar si es un objeto válido
        if (Array.isArray(result) || result === null || result === undefined) {
            return null;
        }
        return result;
    } catch {
        return null;
    }
}

export type FinnhubETFHoldings = { holdings?: Array<{ symbol?: string; name?: string; percent?: number }> };
export const getETFHoldings = cache(async (symbol: string): Promise<FinnhubETFHoldings> => {
    await requireAuthenticatedUser();
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) return { holdings: [] };
        const url = `${FINNHUB_BASE_URL}/etf/holdings?symbol=${encodeURIComponent(symbol)}&token=${token}`;
        const result = await fetchJSON<FinnhubETFHoldings>(url, 6 * 3600);
        // fetchJSON puede retornar array vacío en caso de error, verificar si es un objeto válido
        if (Array.isArray(result) || !result || typeof result !== 'object') {
            return { holdings: [] };
        }
        return result;
    } catch {
        return { holdings: [] };
    }
});

export async function getNews(symbols?: string[]): Promise<MarketNewsArticle[]> {
    await requireAuthenticatedUser();
    try {
        // Use new multi-source news aggregation for better coverage
        const { getNewsWithFallback } = await import('./newsSources.actions');
        const news = await getNewsWithFallback(symbols, 6);

        // If multi-source returns results, use them
        if (news && news.length > 0) {
            return news;
        }

        // Fallback to original Finnhub-only implementation
        const range = getDateRange(5);
        const token = env.FINNHUB_API_KEY;
        if (!token) {
            throw new Error('FINNHUB API key is not configured');
        }
        const cleanSymbols = (symbols || [])
            .map((s) => s?.trim().toUpperCase())
            .filter((s): s is string => Boolean(s));

        const maxArticles = 6;

        // If we have symbols, try to fetch company news per symbol and round-robin select
        // Limitar a máximo 3 símbolos para evitar rate limiting
        if (cleanSymbols.length > 0) {
            const limitedSymbols = cleanSymbols.slice(0, 3); // Limitar a 3 símbolos

            // Requests en paralelo: cada símbolo es independiente y fetchJSON
            // ya cachea 60s, así que el coste pasa de suma a máximo de RTTs.
            const perSymbolResults = await Promise.all(
                limitedSymbols.map(async (sym) => {
                    try {
                        const url = `${FINNHUB_BASE_URL}/company-news?symbol=${encodeURIComponent(sym)}&from=${range.from}&to=${range.to}&token=${token}`;
                        // Noticias siempre frescas - máximo 60 segundos de cache
                        const articles = await fetchJSON<RawNewsArticle[]>(url, 60);
                        return { sym, articles: (articles || []).filter(validateArticle) };
                    } catch {
                        // Silenciar errores 429 (rate limit): ese símbolo aporta []
                        // y el resto continúa; el fallback a generales sigue abajo.
                        return { sym, articles: [] as RawNewsArticle[] };
                    }
                }),
            );
            const perSymbolArticles: Record<string, RawNewsArticle[]> = {};
            for (const { sym, articles } of perSymbolResults) {
                perSymbolArticles[sym] = articles;
            }

            const collected: MarketNewsArticle[] = [];
            // Round-robin up to 6 picks
            for (let round = 0; round < maxArticles; round++) {
                for (let i = 0; i < cleanSymbols.length; i++) {
                    const sym = cleanSymbols[i];
                    const list = perSymbolArticles[sym] || [];
                    if (list.length === 0) continue;
                    const article = list.shift();
                    if (!article || !validateArticle(article)) continue;
                    collected.push(formatArticle(article, true, sym, round));
                    if (collected.length >= maxArticles) break;
                }
                if (collected.length >= maxArticles) break;
            }

            if (collected.length > 0) {
                // Sort by datetime desc
                collected.sort((a, b) => (b.datetime || 0) - (a.datetime || 0));
                return collected.slice(0, maxArticles);
            }
            // If none collected, fall through to general news
        }

        // General market news fallback or when no symbols provided
        // Noticias siempre frescas - máximo 60 segundos de cache
        const generalUrl = `${FINNHUB_BASE_URL}/news?category=general&token=${token}`;
        const general = await fetchJSON<RawNewsArticle[]>(generalUrl, 60);

        const seen = new Set<string>();
        const unique: RawNewsArticle[] = [];
        for (const art of general || []) {
            if (!validateArticle(art)) continue;
            const key = `${art.id}-${art.url}-${art.headline}`;
            if (seen.has(key)) continue;
            seen.add(key);
            unique.push(art);
            if (unique.length >= 20) break; // cap early before final slicing
        }

        const formatted = unique.slice(0, maxArticles).map((a, idx) => formatArticle(a, false, undefined, idx));
        return formatted;
    } catch (err) {
        console.error('getNews error:', err);
        throw new Error('Failed to fetch news');
    }
}

export async function getCompanyNews(symbol: string, maxArticles = 20): Promise<MarketNewsArticle[]> {
    await requireAuthenticatedUser();
    try {
        // Use new multi-source news aggregation for better coverage
        const { getCompanyNewsWithFallback } = await import('./newsSources.actions');
        const news = await getCompanyNewsWithFallback(symbol, maxArticles);

        // If multi-source returns results, use them
        if (news && news.length > 0) {
            return news;
        }

        // Fallback to original Finnhub-only implementation
        const range = getDateRange(30); // Últimos 30 días
        const token = env.FINNHUB_API_KEY;
        if (!token) {
            console.warn('FINNHUB API key not configured, returning empty news');
            return [];
        }

        const url = `${FINNHUB_BASE_URL}/company-news?symbol=${encodeURIComponent(symbol)}&from=${range.from}&to=${range.to}&token=${token}`;
        // Noticias siempre frescas - máximo 60 segundos de cache
        const articles = await fetchJSON<RawNewsArticle[]>(url, 60).catch(() => []);

        if (!Array.isArray(articles)) {
            return [];
        }

        const validArticles = articles
            .filter(validateArticle)
            .sort((a, b) => (b.datetime || 0) - (a.datetime || 0)) // Más recientes primero
            .slice(0, maxArticles)
            .map((article, idx) => formatArticle(article, true, symbol, idx));

        return validArticles;
    } catch (error) {
        console.error('Error fetching company news for', symbol, error);
        return [];
    }
}

export type CompanyEvent = {
    date: string;
    event: string;
    description?: string;
    importance: 'high' | 'medium' | 'low';
};

export async function getCompanyEvents(symbol: string): Promise<CompanyEvent[]> {
    await requireAuthenticatedUser();
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) return [];

        const events: CompanyEvent[] = [];
        const today = new Date();
        const nextYear = new Date(today.getFullYear() + 1, today.getMonth(), today.getDate());

        // Obtener earnings calendar (próximos resultados)
        try {
            const earningsUrl = `${FINNHUB_BASE_URL}/calendar/earnings?symbol=${encodeURIComponent(symbol)}&from=${today.toISOString().split('T')[0]}&to=${nextYear.toISOString().split('T')[0]}&token=${token}`;
            const earnings = await fetchJSON<any>(earningsUrl, 3600).catch(() => null);

            if (earnings?.earningsCalendar && Array.isArray(earnings.earningsCalendar)) {
                earnings.earningsCalendar.slice(0, 8).forEach((item: any) => {
                    if (item.date) {
                        events.push({
                            date: item.date,
                            event: `Earnings Report - Q${item.quarter || 'N/A'} ${item.year || ''}`,
                            description: `Expected earnings announcement. Previous EPS: ${item.epsEstimate ? '$' + item.epsEstimate : 'N/A'}`,
                            importance: 'high',
                        });
                    }
                });
            }
        } catch (e) {
            console.warn('Error fetching earnings calendar for', symbol, e);
        }

        // Obtener IPO date si está disponible en el profile
        // Esto se agregará cuando obtengamos el profile

        // Ordenar eventos por fecha
        events.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

        return events;
    } catch (error) {
        console.error('Error fetching company events for', symbol, error);
        return [];
    }
}

export async function getTechnicalAnalysis(symbol: string, days = 252): Promise<{
    support?: number;
    resistance?: number;
    trend?: 'up' | 'down' | 'sideways';
    avgVolume?: number;
    volumeTrend?: 'increasing' | 'decreasing' | 'stable';
} | null> {
    await requireAuthenticatedUser();
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) return null;

        const to = Math.floor(Date.now() / 1000);
        const from = to - (days * 24 * 60 * 60);

        const candles = await getCandles(symbol, from, to, 'D', 3600);

        if (!candles || candles.s === 'no_data' || candles.c.length === 0) {
            return null;
        }

        const prices = candles.c;
        const volumes = candles.v;
        const highs = candles.h;
        const lows = candles.l;

        // Soporte y resistencia simples (últimos 60 días)
        const recentHighs = highs.slice(-60);
        const recentLows = lows.slice(-60);

        const support = Math.min(...recentLows);
        const resistance = Math.max(...recentHighs);

        // Tendencias (comparar últimos 20 días vs anteriores 20 días)
        const recentAvg = prices.slice(-20).reduce((a, b) => a + b, 0) / 20;
        const previousAvg = prices.slice(-40, -20).reduce((a, b) => a + b, 0) / 20;
        let trend: 'up' | 'down' | 'sideways' = 'sideways';
        const changePercent = ((recentAvg - previousAvg) / previousAvg) * 100;
        if (changePercent > 3) trend = 'up';
        else if (changePercent < -3) trend = 'down';

        // Análisis de volumen
        const avgVolume = volumes.slice(-20).reduce((a, b) => a + b, 0) / 20;
        const previousAvgVolume = volumes.slice(-40, -20).reduce((a, b) => a + b, 0) / 20;
        let volumeTrend: 'increasing' | 'decreasing' | 'stable' = 'stable';
        const volumeChangePercent = ((avgVolume - previousAvgVolume) / previousAvgVolume) * 100;
        if (volumeChangePercent > 10) volumeTrend = 'increasing';
        else if (volumeChangePercent < -10) volumeTrend = 'decreasing';

        return { support, resistance, trend, avgVolume, volumeTrend };
    } catch (error) {
        console.error('Error calculating technical analysis for', symbol, error);
        return null;
    }
}

export async function getIndexComparison(symbol: string): Promise<{
    vsSP500?: { change: number; symbol: string };
    vsSector?: { change: number; sector: string };
} | null> {
    await requireAuthenticatedUser();
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) return null;

        // Obtener datos de S&P 500 y la acción
        const to = Math.floor(Date.now() / 1000);
        const from = to - (252 * 24 * 60 * 60); // 1 año

        const [stockCandles, sp500Candles] = await Promise.all([
            getCandles(symbol, from, to, 'D', 3600).catch(() => null),
            getCandles('SPY', from, to, 'D', 3600).catch(() => null), // S&P 500 ETF
        ]);

        if (!stockCandles || stockCandles.s === 'no_data' || !sp500Candles || sp500Candles.s === 'no_data') {
            return null;
        }

        const stockPrices = stockCandles.c;
        const sp500Prices = sp500Candles.c;

        if (stockPrices.length === 0 || sp500Prices.length === 0) {
            return null;
        }

        // Calcular rendimiento en los últimos 252 días (1 año)
        const stockStart = stockPrices[0];
        const stockEnd = stockPrices[stockPrices.length - 1];
        const sp500Start = sp500Prices[0];
        const sp500End = sp500Prices[sp500Prices.length - 1];

        const stockReturn = ((stockEnd - stockStart) / stockStart) * 100;
        const sp500Return = ((sp500End - sp500Start) / sp500Start) * 100;
        const vsSP500Change = stockReturn - sp500Return;

        return {
            vsSP500: {
                change: vsSP500Change,
                symbol: 'S&P 500',
            },
        };
    } catch (error) {
        console.error('Error calculating index comparison for', symbol, error);
        return null;
    }
}

export async function getStockFinancialData(symbol: string): Promise<{
    quote: any;
    profile: FinnhubProfile2 | null;
    metrics: any;
    news?: MarketNewsArticle[];
    events?: CompanyEvent[];
    analystRecommendations?: any;
    peers?: string[];
    technicalAnalysis?: any;
    indexComparison?: any;
    insiderTrading?: any;
    esgData?: any;
} | null> {
    await requireAuthenticatedUser();
    try {
        const token = env.FINNHUB_API_KEY;
        // console.log("DEBUG: getStockFinancialData token present?", !!token);
        if (!token) {
            console.error("DEBUG: No Finnhub token found in env");
            return null;
        }

        // Start all requests in parallel
        const quotePromise = fetchJSON<any>(`${FINNHUB_BASE_URL}/quote?symbol=${encodeURIComponent(symbol)}&token=${token}`, 60).catch(() => null);
        const profilePromise = fetchJSON<FinnhubProfile2>(`${FINNHUB_BASE_URL}/stock/profile2?symbol=${encodeURIComponent(symbol)}&token=${token}`, 86400).catch(() => null);
        const metricsPromise = fetchJSON<any>(`${FINNHUB_BASE_URL}/stock/metric?symbol=${encodeURIComponent(symbol)}&metric=all&token=${token}`, 86400).catch(() => ({ metric: {} }));
        const newsPromise = getCompanyNews(symbol, 10).catch(() => []);

        const eventsUrl = `${FINNHUB_BASE_URL}/stock/earnings-calendar?symbol=${encodeURIComponent(symbol)}&from=${Math.floor(Date.now() / 1000) - (90 * 24 * 60 * 60)}&to=${Math.floor(Date.now() / 1000) + (90 * 24 * 60 * 60)}&token=${token}`;
        const eventsPromise = fetchJSON<any>(eventsUrl, 86400).catch(() => null);

        const recUrl = `${FINNHUB_BASE_URL}/stock/recommendation?symbol=${encodeURIComponent(symbol)}&token=${token}`;
        const recPromise = fetchJSON<any>(recUrl, 86400).catch(() => null);

        const indexComparisonPromise = getIndexComparison(symbol).catch(() => null);

        const peersUrl = `${FINNHUB_BASE_URL}/stock/peers?symbol=${encodeURIComponent(symbol)}&token=${token}`;
        const peersPromise = fetchJSON<string[]>(peersUrl, 86400).catch(() => null);

        const insiderUrl = `${FINNHUB_BASE_URL}/stock/insider-transactions?symbol=${encodeURIComponent(symbol)}&token=${token}`;
        const insiderPromise = fetchJSON<any>(insiderUrl, 86400).catch(() => null);

        // Await all promises
        const [
            quote,
            profile,
            metrics,
            newsArticles,
            eventsData,
            recData,
            indexComparison,
            peersData,
            insiderTrading
        ] = await Promise.all([
            quotePromise,
            profilePromise,
            metricsPromise,
            newsPromise,
            eventsPromise,
            recPromise,
            indexComparisonPromise,
            peersPromise,
            insiderPromise
        ]);

        // Process Events
        let events: CompanyEvent[] = [];
        if (eventsData && Array.isArray(eventsData.earningsCalendar)) {
            events = eventsData.earningsCalendar.map((e: any) => ({
                date: e.date || '',
                event: e.event || 'Earnings',
                description: `EPS Estimate: ${e.epsEstimate || 'N/A'}, EPS Actual: ${e.epsActual || 'N/A'}`,
                importance: 'high' as const,
            }));
        }
        if (profile?.ipo) {
            events.push({
                date: profile.ipo,
                event: 'IPO Date',
                description: `Initial Public Offering date`,
                importance: 'low',
            });
        }

        // Process Recommendations
        let analystRecommendations: any = null;
        let targetPrice: any = null;
        if (recData && Array.isArray(recData) && recData.length > 0) {
            analystRecommendations = recData[0]; // Recent
            if (recData[0].targetMeanPrice) {
                targetPrice = {
                    targetMeanPrice: recData[0].targetMeanPrice,
                    targetHigh: recData[0].targetHigh,
                    targetLow: recData[0].targetLow,
                };
            }
        }

        // Process Peers
        let peers: string[] = [];
        if (Array.isArray(peersData)) {
            peers = peersData.filter(p => p && p !== symbol).slice(0, 10);
        }

        return {
            quote,
            profile,
            metrics,
            news: newsArticles,
            events,
            analystRecommendations: analystRecommendations || targetPrice,
            peers,
            technicalAnalysis: null,
            indexComparison,
            insiderTrading,
            esgData: null,
        };
    } catch (error) {
        console.error('Error fetching financial data for', symbol, error);
        return null;
    }
}

/**
 * Lightweight version of getStockFinancialData for ProPicks
 * Only fetches essential data (quote, profile, metrics) - skips news, events, peers etc.
 * Much faster for bulk operations like ProPicks
 */
export async function getStockFinancialDataLight(symbol: string): Promise<{
    quote: any;
    profile: FinnhubProfile2 | null;
    metrics: any;
    priceTarget: any;
} | null> {
    await requireAuthenticatedUser();
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) {
            return null;
        }

        // Only fetch essential data - no news, events, peers etc.
        const [quote, profile, metrics, priceTarget] = await Promise.all([
            fetchJSON<any>(`${FINNHUB_BASE_URL}/quote?symbol=${encodeURIComponent(symbol)}&token=${token}`, 60).catch(() => null),
            fetchJSON<FinnhubProfile2>(`${FINNHUB_BASE_URL}/stock/profile2?symbol=${encodeURIComponent(symbol)}&token=${token}`, 86400).catch(() => null),
            fetchJSON<any>(`${FINNHUB_BASE_URL}/stock/metric?symbol=${encodeURIComponent(symbol)}&metric=all&token=${token}`, 86400).catch(() => ({ metric: {} })),
            fetchJSON<any>(`${FINNHUB_BASE_URL}/stock/price-target?symbol=${encodeURIComponent(symbol)}&token=${token}`, 86400).catch(() => null),
        ]);

        return { quote, profile, metrics, priceTarget };
    } catch {
        // Silently fail for light version
        return null;
    }
}


// Finnhub /search no devuelve la bolsa; el displaySymbol lleva el sufijo de
// mercado (SAN.MC, IBE.MC, AIR.PA...). Mapa de sufijos frecuentes; si el
// sufijo es desconocido se muestra tal cual (mas honesto que asumir 'US').
const EXCHANGE_LABEL_BY_SUFFIX: Record<string, string> = {
    MC: 'BME', // Bolsa de Madrid
    L: 'LSE',
    PA: 'Euronext Paris',
    AS: 'Euronext Amsterdam',
    BR: 'Euronext Brussels',
    LS: 'Euronext Lisbon',
    DE: 'XETRA',
    F: 'Frankfurt',
    MI: 'Borsa Italiana',
    SW: 'SIX',
    VI: 'Wiener Borse',
    HE: 'Nasdaq Helsinki',
    ST: 'Nasdaq Stockholm',
    CO: 'Nasdaq Copenhagen',
    OL: 'Oslo Bors',
    HK: 'HKEX',
    T: 'TSE',
    AX: 'ASX',
    TO: 'TSX',
    V: 'TSXV',
    MX: 'BMV',
    SA: 'B3',
};

function exchangeFromDisplaySymbol(displaySymbol?: string): string | undefined {
    if (!displaySymbol) return undefined;
    const idx = displaySymbol.lastIndexOf('.');
    if (idx < 0) return 'US';
    const suffix = displaySymbol.slice(idx + 1).toUpperCase();
    return EXCHANGE_LABEL_BY_SUFFIX[suffix] ?? suffix;
}

export const searchStocks = cache(async (query?: string): Promise<StockWithWatchlistStatus[]> => {
    await requireAuthenticatedUser();
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) {
            // Finnhub is optional; the search command renders an explicit empty state.
            return [];
        }

        const trimmed = typeof query === 'string' ? query.trim() : '';

        let results: FinnhubSearchResult[] = [];

        if (!trimmed) {
            // Fetch top 10 popular symbols' profiles
            const top = POPULAR_STOCK_SYMBOLS.slice(0, 10);
            const profiles = await Promise.all(
                top.map(async (sym) => {
                    try {
                        const url = `${FINNHUB_BASE_URL}/stock/profile2?symbol=${encodeURIComponent(sym)}&token=${token}`;
                        // Revalidate every hour
                        const profile = await fetchJSON<any>(url, 3600);
                        return { sym, profile } as { sym: string; profile: any };
                    } catch {
                        // Silently handle Finnhub timeouts - expected with rate limits
                        return { sym, profile: null } as { sym: string; profile: any };
                    }
                })
            );

            results = profiles
                .map(({ sym, profile }) => {
                    const symbol = sym.toUpperCase();
                    const name: string | undefined = profile?.name || profile?.ticker || undefined;
                    const exchange: string | undefined = profile?.exchange || undefined;
                    if (!name) return undefined;
                    const r: FinnhubSearchResult = {
                        symbol,
                        description: name,
                        displaySymbol: symbol,
                        type: 'Common Stock',
                    };
                    // We don't include exchange in FinnhubSearchResult type, so carry via mapping later using profile
                    // To keep pipeline simple, attach exchange via closure map stage
                    // We'll reconstruct exchange when mapping to final type
                    (r as any).__exchange = exchange; // internal only
                    return r;
                })
                .filter((x): x is FinnhubSearchResult => Boolean(x));
        } else {
            const url = `${FINNHUB_BASE_URL}/search?q=${encodeURIComponent(trimmed)}&token=${token}`;
            const data = await fetchJSON<FinnhubSearchResponse>(url, 1800);
            results = Array.isArray(data?.result) ? data.result : [];

            // Un ticker exacto con sufijo de bolsa ("SAN.MC") no matchea en el
            // search de Finnhub (el punto rompe el prefix matching), asi que
            // escribir el simbolo tal cual no devolvia nada y no se podian
            // anadir posiciones EU por ticker. Fallback: busca la parte base
            // ("SAN") y quedate con el resultado cuyo simbolo coincida
            // exactamente con lo pedido, anteponiendolo al resto.
            const upperQuery = trimmed.toUpperCase();
            const matchesExact = (r: FinnhubSearchResult): boolean =>
                (r.symbol || '').toUpperCase() === upperQuery ||
                (r.displaySymbol || '').toUpperCase() === upperQuery;
            if (upperQuery.includes('.') && !results.some(matchesExact)) {
                const base = upperQuery.slice(0, upperQuery.indexOf('.'));
                if (base) {
                    try {
                        const fbUrl = `${FINNHUB_BASE_URL}/search?q=${encodeURIComponent(base)}&token=${token}`;
                        const fbData = await fetchJSON<FinnhubSearchResponse>(fbUrl, 1800);
                        const fbResults = Array.isArray(fbData?.result) ? fbData.result : [];
                        const exact = fbResults.filter(matchesExact);
                        if (exact.length > 0) {
                            results = [...exact, ...results];
                        }
                    } catch {
                        // Fallback opcional: si falla, devolvemos lo que hubiera.
                    }
                }
            }
        }

        const mapped: StockWithWatchlistStatus[] = results
            .map((r) => {
                const upper = (r.symbol || '').toUpperCase();
                const name = r.description || upper;
                const exchangeFromProfile = (r as any).__exchange as string | undefined;
                // displaySymbol es el ticker visible (SAN.MC), NO la bolsa:
                // solo se usa para derivar el mercado por sufijo.
                const exchange = exchangeFromProfile || exchangeFromDisplaySymbol(r.displaySymbol as string | undefined) || 'US';
                const type = r.type || 'Stock';
                const item: StockWithWatchlistStatus = {
                    symbol: upper,
                    name,
                    exchange,
                    type,
                    isInWatchlist: false,
                };
                return item;
            })
            .slice(0, 15);

        return mapped;
    } catch (err) {
        console.error('Error in stock search:', err);
        return [];
    }
});

/**
 * Populares del buscador con ESTADO explicito: `searchStocks()` atrapa todos
 * los errores y devuelve [], indistinguible de "no hay nada que mostrar".
 * Aqui un fallo total de proveedor/red devuelve `error` (el caller reintenta
 * y avisa); la lista vacia valida (sin clave Finnhub) es `ok` con [].
 */
export const getPopularStocks = cache(async (): Promise<PopularStocksResult> => {
    await requireAuthenticatedUser();
    const token = env.FINNHUB_API_KEY;
    if (!token) {
        // Finnhub es opcional: lista vacia valida, no un fallo.
        return { status: 'ok', stocks: [] };
    }
    const top = POPULAR_STOCK_SYMBOLS.slice(0, 10);
    const profiles = await Promise.all(
        top.map(async (sym) => {
            try {
                const url = `${FINNHUB_BASE_URL}/stock/profile2?symbol=${encodeURIComponent(sym)}&token=${token}`;
                const profile = await fetchJSON<any>(url, 3600);
                return { sym, profile } as { sym: string; profile: any };
            } catch {
                return { sym, profile: null } as { sym: string; profile: any };
            }
        })
    );
    const successful = profiles.filter(({ profile }) => profile?.name || profile?.ticker);
    if (successful.length === 0) {
        // 0/10 con clave configurada: proveedor o red caidos. NO se cachea
        // como exito: el buscador reintentara y mostrara indicador.
        return { status: 'error' };
    }
    const stocks: StockWithWatchlistStatus[] = successful
        .map(({ sym, profile }) => {
            const symbol = sym.toUpperCase();
            return {
                symbol,
                name: (profile.name || profile.ticker) as string,
                exchange: (profile.exchange as string | undefined) || 'US',
                type: 'Common Stock',
                isInWatchlist: false,
            };
        })
        .slice(0, 10);
    return { status: 'ok', stocks };
});

// Helper para obtener solo la cotización (más ligero que getStockFinancialData)
export async function getStockQuote(symbol: string): Promise<{ c: number; d: number; dp: number; h: number; l: number; o: number; pc: number; } | null> {
    await requireAuthenticatedUser();
    // Caché corta en memoria (45s): quote se llama en bucle (watchlist,
    // screener, oportunidades) y el dato es idéntico dentro de la ventana.
    // Los misses (null) no se cachean.
    return cachedFetch(
        `finnhub:quote:${symbol.trim().toUpperCase()}`,
        () => fetchStockQuote(symbol),
        45,
    );
}

async function fetchStockQuote(symbol: string): Promise<{ c: number; d: number; dp: number; h: number; l: number; o: number; pc: number; } | null> {
    // Try Finnhub first
    try {
        const token = env.FINNHUB_API_KEY;
        if (token) {
            const url = `${FINNHUB_BASE_URL}/quote?symbol=${encodeURIComponent(symbol)}&token=${token}`;
            const data = await fetchJSON<any>(url, 60);
            // Verify we got valid data (Finnhub returns all zeros for invalid symbols)
            if (data && (data.c > 0 || data.pc > 0)) {
                return data;
            }
        }
    } catch {
        console.log(`Finnhub quote failed for ${symbol}, trying Yahoo Finance...`);
    }
    
    // Fallback al backend (Yahoo chart API) para mercados que Finnhub free
    // no cubre (IBEX .MC, .PA, .DE...). El backend cachea 60s por símbolo.
    const backendUrl = process.env.FMP_BACKEND_URL;
    if (backendUrl) {
        try {
            const path = `/api/market/quote/${encodeURIComponent(symbol)}`;
            const identityHeaders = await researchIdentityHeaders({
                method: 'GET',
                path,
            });
            const response = await fetch(`${backendUrl}${path}`, {
                headers: identityHeaders,
                // Timeout acotado: un backend caído no debe congelar la página.
                signal: AbortSignal.timeout(5000),
            });
            if (response.ok) {
                const data = await response.json();
                if (data && (data.c > 0 || data.pc > 0)) {
                    return data;
                }
            }
        } catch (error) {
            console.error(`Yahoo Finance quote also failed for ${symbol}:`, error);
        }
    }
    
    return null;
}

export type EarningsEvent = {
    symbol: string;
    date: string;
    quarter: number;
    year: number;
    epsEstimate: number | null;
    hour: string;
};

export async function getUpcomingEarnings(symbols: string[]): Promise<EarningsEvent[]> {
    await requireAuthenticatedUser();
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) return [];

        const today = new Date();
        const nextYear = new Date();
        nextYear.setDate(today.getDate() + 365); // Look ahead 1 year to ensure we find next events

        const fromDate = today.toISOString().split('T')[0];
        const toDate = nextYear.toISOString().split('T')[0];

        // Limit symbols to avoid rate limiting (max 8 symbols)
        const limitedSymbols = symbols.slice(0, 8);

        // Requests en paralelo: cada símbolo es independiente (caché 1h en
        // fetchJSON). El coste pasa de suma+RTTs+sleeps a un solo máximo.
        const perSymbolEarnings = await Promise.all(
            limitedSymbols.map(async (symbol) => {
                try {
                    const url = `${FINNHUB_BASE_URL}/stock/earnings-calendar?symbol=${encodeURIComponent(symbol)}&from=${fromDate}&to=${toDate}&token=${token}`;
                    const data = await fetchJSON<any>(url, 3600); // 1 hour cache

                    if (data && Array.isArray(data.earningsCalendar)) {
                        // Filter for future dates only
                        return data.earningsCalendar
                            .filter((e: any) => e.date >= fromDate)
                            .map((e: any) => ({
                                symbol: e.symbol,
                                date: e.date,
                                quarter: e.quarter,
                                year: e.year,
                                epsEstimate: e.epsEstimate || null,
                                hour: e.hour || '',
                            })) as EarningsEvent[];
                    }
                    return [] as EarningsEvent[];
                } catch (e: any) {
                    // Rate limit u otro error: ese símbolo aporta [] y el
                    // resto continúa (antes un 429 abortaba todo el loop).
                    if (e?.message?.includes('429') || e?.message?.includes('limit') || e?.message?.includes('DOCTYPE')) {
                        console.warn(`Rate limit hit fetching earnings for ${symbol}, skipping symbol`);
                        return [] as EarningsEvent[];
                    }
                    // For other errors, just log and continue
                    console.error(`Error fetching earnings for ${symbol}`, e);
                    return [] as EarningsEvent[];
                }
            }),
        );
        const allEarnings: EarningsEvent[] = perSymbolEarnings.flat();

        // Sort by date
        allEarnings.sort((a, b) => a.date.localeCompare(b.date));

        return allEarnings;
    } catch (error) {
        console.error('Error fetching upcoming earnings:', error);
        return [];
    }
}

// ============================================================================
// NEW FEATURES: Congress Trading, ESG Scores, Institutional Holdings
// ============================================================================

/**
 * Congress Trading - Track stock trades by US Congress members
 */
export type CongressTrade = {
    symbol: string;
    name: string;
    transactionDate: string;
    transactionType: 'buy' | 'sell' | 'exchange';
    amount: string;
    assetDescription: string;
    ownerType: string;
    congress: 'senate' | 'house';
};

export async function getCongressTrading(symbol?: string): Promise<CongressTrade[]> {
    await requireAuthenticatedUser();
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) return [];

        // Get date range (last 365 days)
        const to = new Date().toISOString().split('T')[0];
        const fromDate = new Date();
        fromDate.setDate(fromDate.getDate() - 365);
        const from = fromDate.toISOString().split('T')[0];

        let url: string;
        if (symbol) {
            url = `${FINNHUB_BASE_URL}/stock/congressional-trading?symbol=${encodeURIComponent(symbol)}&from=${from}&to=${to}&token=${token}`;
        } else {
            url = `${FINNHUB_BASE_URL}/stock/congressional-trading?from=${from}&to=${to}&token=${token}`;
        }

        const data = await fetchJSON<any>(url, 3600); // Cache 1 hour

        if (!data || !Array.isArray(data.data)) {
            return [];
        }

        return data.data.map((trade: any) => ({
            symbol: trade.symbol || '',
            name: trade.name || '',
            transactionDate: trade.transactionDate || '',
            transactionType: trade.transactionType?.toLowerCase() || 'buy',
            amount: trade.amount || '',
            assetDescription: trade.assetDescription || '',
            ownerType: trade.ownerType || 'N/A',
            congress: trade.congress || 'senate',
        })).slice(0, 100); // Limit to 100 most recent
    } catch (error) {
        console.error('Error fetching congress trading:', error);
        return [];
    }
}

/**
 * ESG Scores - Environmental, Social, and Governance ratings
 */
export type ESGScore = {
    symbol: string;
    totalESG: number;
    environmentalScore: number;
    socialScore: number;
    governanceScore: number;
    lastRefreshDate: string;
    level: string;
    peersCount: number;
    percentile: number;
};

export async function getESGScores(symbol: string): Promise<ESGScore | null> {
    await requireAuthenticatedUser();
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) return null;

        const url = `${FINNHUB_BASE_URL}/stock/esg?symbol=${encodeURIComponent(symbol)}&token=${token}`;
        const data = await fetchJSON<any>(url, 86400); // Cache 24 hours (ESG scores don't change often)

        if (!data || !data.totalESG) {
            return null;
        }

        return {
            symbol: symbol,
            totalESG: data.totalESG || 0,
            environmentalScore: data.environmentalScore || 0,
            socialScore: data.socialScore || 0,
            governanceScore: data.governanceScore || 0,
            lastRefreshDate: data.lastRefreshDate || '',
            level: data.level || 'N/A',
            peersCount: data.peersCount || 0,
            percentile: data.percentile || 0,
        };
    } catch (error) {
        console.error('Error fetching ESG scores for', symbol, error);
        return null;
    }
}

/**
 * Institutional Holdings (13F) - Track what major funds are holding
 */
export type InstitutionalHolder = {
    name: string;
    share: number;
    change: number;
    filingDate: string;
    value: number;
};

export type InstitutionalOwnership = {
    symbol: string;
    holders: InstitutionalHolder[];
    ownershipPercent: number;
};

export async function getInstitutionalHoldings(symbol: string): Promise<InstitutionalOwnership | null> {
    await requireAuthenticatedUser();
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) return null;

        const url = `${FINNHUB_BASE_URL}/stock/ownership?symbol=${encodeURIComponent(symbol)}&token=${token}`;
        const data = await fetchJSON<any>(url, 86400); // Cache 24 hours

        if (!data || !Array.isArray(data.ownership)) {
            return null;
        }

        const holders: InstitutionalHolder[] = data.ownership
            .slice(0, 20) // Top 20 holders
            .map((h: any) => ({
                name: h.name || 'Desconocido',
                share: h.share || 0,
                change: h.change || 0,
                filingDate: h.filingDate || '',
                value: h.value || 0,
            }));

        // Calculate total ownership percent
        const ownershipPercent = data.ownershipPercent || 0;

        return {
            symbol,
            holders,
            ownershipPercent,
        };
    } catch (error) {
        console.error('Error fetching institutional holdings for', symbol, error);
        return null;
    }
}

/**
 * Senate Lobbying - Track lobbying activities
 */
export type LobbyingActivity = {
    symbol: string;
    year: number;
    quarter: number;
    income: number;
    expenses: number;
    documentUrl: string;
    name: string;
};

export async function getLobbyingData(symbol: string): Promise<LobbyingActivity[]> {
    await requireAuthenticatedUser();
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) return [];

        const to = new Date().toISOString().split('T')[0];
        const fromDate = new Date();
        fromDate.setFullYear(fromDate.getFullYear() - 2); // Last 2 years
        const from = fromDate.toISOString().split('T')[0];

        const url = `${FINNHUB_BASE_URL}/stock/lobbying?symbol=${encodeURIComponent(symbol)}&from=${from}&to=${to}&token=${token}`;
        const data = await fetchJSON<any>(url, 86400);

        if (!data || !Array.isArray(data.data)) {
            return [];
        }

        return data.data.map((item: any) => ({
            symbol: item.symbol || symbol,
            year: item.year || 0,
            quarter: item.quarter || 0,
            income: item.income || 0,
            expenses: item.expenses || 0,
            documentUrl: item.documentUrl || '',
            name: item.name || '',
        })).slice(0, 20);
    } catch (error) {
        console.error('Error fetching lobbying data for', symbol, error);
        return [];
    }
}

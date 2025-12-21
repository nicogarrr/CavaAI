'use server';

import { getDateRange, validateArticle, formatArticle } from '@/lib/utils';
import { POPULAR_STOCK_SYMBOLS } from '@/lib/constants';
import { cache } from 'react';
import { requestCache } from '@/lib/cache/requestCache';

import { env } from '@/lib/env';
import { TIMEOUTS } from '@/lib/constants';
import { ExternalAPIError, RateLimitError, toAppError } from '@/lib/types/errors';

const FINNHUB_BASE_URL = env.FINNHUB_BASE_URL;

/**
 * Función helper para fetch con manejo de errores apropiado
 * Lanza errores tipados en lugar de retornar arrays vacíos silenciosamente
 */
async function fetchJSON<T>(url: string, revalidateSeconds?: number): Promise<T> {
    // Para datos críticos como precios y noticias, usar cache mínimo (30-60 segundos)
    // Para datos estáticos como perfiles, permitir cache más largo
    const options: RequestInit & { next?: { revalidate?: number } } = revalidateSeconds && revalidateSeconds > 0
        ? { cache: 'force-cache', next: { revalidate: revalidateSeconds } }
        : { cache: 'no-store' };

    // Timeout usando constante centralizada
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), TIMEOUTS.API_REQUEST);

    try {
        const res = await fetch(url, { ...options, signal: controller.signal });
        clearTimeout(timeoutId);

        if (!res.ok) {
            // Lanzar errores apropiados en lugar de retornar arrays vacíos
            if (res.status === 429) {
                throw new RateLimitError(`API rate limit reached for ${url}`);
            }

            if (res.status >= 500) {
                throw new ExternalAPIError(
                    `External API error (${res.status}) for ${url}`,
                    'finnhub',
                    { status: res.status, statusText: res.statusText }
                );
            }

            throw new ExternalAPIError(
                `Failed to fetch ${url}: ${res.status} ${res.statusText}`,
                'finnhub',
                { status: res.status }
            );
        }
        
        // Verificar que la respuesta sea JSON antes de parsear
        const contentType = res.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
            // Finnhub a veces devuelve HTML cuando hay rate limit o errores
            const text = await res.text();
            if (text.startsWith('<!DOCTYPE') || text.startsWith('<html')) {
                throw new RateLimitError(`Finnhub returned HTML instead of JSON (likely rate limited)`);
            }
            // Intentar parsear de todos modos si no es HTML
            try {
                return JSON.parse(text) as T;
            } catch {
                throw new ExternalAPIError(`Invalid response format from Finnhub`, 'finnhub');
            }
        }
        
        return (await res.json()) as T;
    } catch (error: unknown) {
        clearTimeout(timeoutId);

        // Si es un error de nuestra aplicación, re-lanzarlo
        if (error instanceof RateLimitError || error instanceof ExternalAPIError) {
            throw error;
        }

        // Manejar otros errores
        const appError = toAppError(error);
        if (appError.message.includes('AbortError') || appError.message.includes('aborted')) {
            throw new ExternalAPIError(
                `Request timeout for ${url}`,
                'finnhub',
                appError
            );
        }

        throw new ExternalAPIError(
            `Unexpected error fetching ${url}`,
            'finnhub',
            appError
        );
    }
}

export { fetchJSON };

export type FinnhubCandles = { s: 'ok' | 'no_data'; c: number[]; t: number[]; o: number[]; h: number[]; l: number[]; v: number[] };

export async function getCandles(symbol: string, from: number, to: number, resolution: 'D' | 'W' | 'M' | '60' = 'D', revalidateSeconds = 1800): Promise<FinnhubCandles> {
    const token = env.FINNHUB_API_KEY;
    if (!token) {
        // Sin API key, devolver datos vacíos en lugar de lanzar error
        return { s: 'no_data', c: [], t: [], o: [], h: [], l: [], v: [] };
    }
    const url = `${FINNHUB_BASE_URL}/stock/candle?symbol=${encodeURIComponent(symbol)}&resolution=${resolution}&from=${from}&to=${to}&token=${token}`;
    try {
        const result = await fetchJSON<FinnhubCandles>(url, revalidateSeconds);
        // fetchJSON puede retornar array vacío en caso de error, verificar si es un objeto válido
        if (Array.isArray(result) || !result || typeof result !== 'object') {
            return { s: 'no_data', c: [], t: [], o: [], h: [], l: [], v: [] };
        }
        return result;
    } catch (e) {
        // Si el plan no permite el recurso (403) u otro error, devolvemos sin datos para no romper la UI
        return { s: 'no_data', c: [], t: [], o: [], h: [], l: [], v: [] };
    }
}

export type FinnhubProfile2 = { ticker?: string; name?: string; exchange?: string; currency?: string; country?: string; ipo?: string; logo?: string; weburl?: string };
export const getProfile = cache(async (symbol: string): Promise<FinnhubProfile2 | null> => {
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
});

export type FinnhubETFHoldings = { holdings?: Array<{ symbol?: string; name?: string; percent?: number }> };
export const getETFHoldings = cache(async (symbol: string): Promise<FinnhubETFHoldings> => {
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
            const perSymbolArticles: Record<string, RawNewsArticle[]> = {};
            const limitedSymbols = cleanSymbols.slice(0, 3); // Limitar a 3 símbolos

            // Hacer requests secuenciales con delay para evitar rate limiting
            for (const sym of limitedSymbols) {
                try {
                    const url = `${FINNHUB_BASE_URL}/company-news?symbol=${encodeURIComponent(sym)}&from=${range.from}&to=${range.to}&token=${token}`;
                    // Noticias siempre frescas - máximo 60 segundos de cache
                    const articles = await fetchJSON<RawNewsArticle[]>(url, 60);
                    perSymbolArticles[sym] = (articles || []).filter(validateArticle);

                    // Delay de 200ms entre requests para evitar rate limiting
                    if (limitedSymbols.indexOf(sym) < limitedSymbols.length - 1) {
                        await new Promise(resolve => setTimeout(resolve, 200));
                    }
                } catch (e: any) {
                    // Silenciar errores 429 (rate limit) y continuar
                    if (e?.message?.includes('429') || e?.message?.includes('limit')) {
                        // Si alcanzamos el límite, usar noticias generales
                        break;
                    }
                    perSymbolArticles[sym] = [];
                }
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
        const recentPrices = prices.slice(-60);
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
    } catch (error) {
        // Silently fail for light version
        return null;
    }
}

export const searchStocks = cache(async (query?: string): Promise<StockWithWatchlistStatus[]> => {
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) {
            // If no token, log and return empty to avoid throwing per requirements
            console.error('Error in stock search:', new Error('FINNHUB API key is not configured'));
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
                    } catch (e) {
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
        }

        const mapped: StockWithWatchlistStatus[] = results
            .map((r) => {
                const upper = (r.symbol || '').toUpperCase();
                const name = r.description || upper;
                const exchangeFromDisplay = (r.displaySymbol as string | undefined) || undefined;
                const exchangeFromProfile = (r as any).__exchange as string | undefined;
                const exchange = exchangeFromDisplay || exchangeFromProfile || 'US';
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

// Helper para obtener solo la cotización (más ligero que getStockFinancialData)
export async function getStockQuote(symbol: string): Promise<{ c: number; d: number; dp: number; h: number; l: number; o: number; pc: number; } | null> {
    try {
        const token = env.FINNHUB_API_KEY;
        if (!token) return null;
        const url = `${FINNHUB_BASE_URL}/quote?symbol=${encodeURIComponent(symbol)}&token=${token}`;
        return await fetchJSON<any>(url, 60);
    } catch {
        return null;
    }
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
        const allEarnings: EarningsEvent[] = [];

        // Fetch earnings SEQUENTIALLY with delay to avoid rate limiting
        for (let i = 0; i < limitedSymbols.length; i++) {
            const symbol = limitedSymbols[i];
            try {
                const url = `${FINNHUB_BASE_URL}/stock/earnings-calendar?symbol=${encodeURIComponent(symbol)}&from=${fromDate}&to=${toDate}&token=${token}`;
                const data = await fetchJSON<any>(url, 3600); // 1 hour cache

                if (data && Array.isArray(data.earningsCalendar)) {
                    // Filter for future dates only
                    const events = data.earningsCalendar
                        .filter((e: any) => e.date >= fromDate)
                        .map((e: any) => ({
                            symbol: e.symbol,
                            date: e.date,
                            quarter: e.quarter,
                            year: e.year,
                            epsEstimate: e.epsEstimate || null,
                            hour: e.hour || '',
                        }));
                    allEarnings.push(...events);
                }

                // Add delay between requests to avoid rate limiting (300ms)
                // Skip delay for the last symbol
                if (i < limitedSymbols.length - 1) {
                    await new Promise(resolve => setTimeout(resolve, 300));
                }
            } catch (e: any) {
                // If we hit rate limit, stop making more requests
                if (e?.message?.includes('429') || e?.message?.includes('limit') || e?.message?.includes('DOCTYPE')) {
                    console.warn(`Rate limit hit after ${i + 1} symbols, stopping earnings fetch`);
                    break;
                }
                // For other errors, just log and continue
                console.error(`Error fetching earnings for ${symbol}`, e);
            }
        }

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
                name: h.name || 'Unknown',
                share: h.share || 0,
                change: h.change || 0,
                filingDate: h.filingDate || '',
                value: h.value || 0,
            }));

        // Calculate total ownership percent
        const totalShares = holders.reduce((sum, h) => sum + h.share, 0);
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

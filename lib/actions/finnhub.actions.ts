'use server';

import { getDateRange, validateArticle, formatArticle } from '@/lib/utils';
import { POPULAR_STOCK_SYMBOLS } from '@/lib/constants';
import { cache } from 'react';

const FINNHUB_BASE_URL = 'https://finnhub.io/api/v1';
const NEXT_PUBLIC_FINNHUB_API_KEY = process.env.NEXT_PUBLIC_FINNHUB_API_KEY ?? '';

async function fetchJSON<T>(url: string, revalidateSeconds?: number): Promise<T> {
    const options: RequestInit & { next?: { revalidate?: number } } = revalidateSeconds
        ? { cache: 'force-cache', next: { revalidate: revalidateSeconds } }
        : { cache: 'no-store' };

    // Timeout de 10 segundos para evitar que fetch bloquee indefinidamente
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    try {
        const res = await fetch(url, { ...options, signal: controller.signal });
        clearTimeout(timeoutId);
        
        if (!res.ok) {
            const text = await res.text().catch(() => '');
            // Si es error 429, retornar array vacío en lugar de lanzar error
            if (res.status === 429) {
                console.warn('API rate limit reached, returning empty result');
                return [] as T;
            }
            // Para otros errores, también retornar array vacío en lugar de lanzar error
            // para evitar que bloquee la navegación
            console.warn(`Fetch failed ${res.status} for ${url}, returning empty result`);
            return [] as T;
        }
        return (await res.json()) as T;
    } catch (error: any) {
        clearTimeout(timeoutId);
        // Si es aborto por timeout o cualquier otro error, retornar array vacío
        // para evitar que bloquee la navegación
        if (error.name === 'AbortError') {
            console.warn(`Fetch timeout for ${url}, returning empty result`);
        } else {
            console.warn(`Fetch error for ${url}:`, error.message || error, 'returning empty result');
        }
        return [] as T;
    }
}

export { fetchJSON };

export type FinnhubCandles = { s: 'ok' | 'no_data'; c: number[]; t: number[]; o: number[]; h: number[]; l: number[]; v: number[] };

export async function getCandles(symbol: string, from: number, to: number, resolution: 'D' | 'W' | 'M' | '60' = 'D', revalidateSeconds = 3600): Promise<FinnhubCandles> {
    const token = process.env.FINNHUB_API_KEY ?? NEXT_PUBLIC_FINNHUB_API_KEY;
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
        const token = process.env.FINNHUB_API_KEY ?? NEXT_PUBLIC_FINNHUB_API_KEY;
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
        const token = process.env.FINNHUB_API_KEY ?? NEXT_PUBLIC_FINNHUB_API_KEY;
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
        const range = getDateRange(5);
        const token = process.env.FINNHUB_API_KEY ?? NEXT_PUBLIC_FINNHUB_API_KEY;
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
                    const articles = await fetchJSON<RawNewsArticle[]>(url, 300);
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
        const generalUrl = `${FINNHUB_BASE_URL}/news?category=general&token=${token}`;
        const general = await fetchJSON<RawNewsArticle[]>(generalUrl, 300);

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
        const range = getDateRange(30); // Últimos 30 días
        const token = process.env.FINNHUB_API_KEY ?? NEXT_PUBLIC_FINNHUB_API_KEY;
        if (!token) {
            console.warn('FINNHUB API key not configured, returning empty news');
            return [];
        }

        const url = `${FINNHUB_BASE_URL}/company-news?symbol=${encodeURIComponent(symbol)}&from=${range.from}&to=${range.to}&token=${token}`;
        const articles = await fetchJSON<RawNewsArticle[]>(url, 300).catch(() => []);

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
        const token = process.env.FINNHUB_API_KEY ?? NEXT_PUBLIC_FINNHUB_API_KEY;
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
        const token = process.env.FINNHUB_API_KEY ?? NEXT_PUBLIC_FINNHUB_API_KEY;
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
        const token = process.env.FINNHUB_API_KEY ?? NEXT_PUBLIC_FINNHUB_API_KEY;
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
        const token = process.env.FINNHUB_API_KEY ?? NEXT_PUBLIC_FINNHUB_API_KEY;
        if (!token) return null;

        // Obtener datos críticos secuencialmente con delays para evitar rate limiting
        const quote = await fetchJSON<any>(`${FINNHUB_BASE_URL}/quote?symbol=${encodeURIComponent(symbol)}&token=${token}`, 300).catch(() => null);
        
        // Delay pequeño entre requests
        await new Promise(resolve => setTimeout(resolve, 150));
        
        const profile = await fetchJSON<FinnhubProfile2>(`${FINNHUB_BASE_URL}/stock/profile2?symbol=${encodeURIComponent(symbol)}&token=${token}`, 3600).catch(() => null);
        
        // Delay pequeño entre requests
        await new Promise(resolve => setTimeout(resolve, 150));
        
        const metrics = await fetchJSON<any>(`${FINNHUB_BASE_URL}/stock/metric?symbol=${encodeURIComponent(symbol)}&metric=all&token=${token}`, 3600).catch(() => ({ metric: {} }));

        // Obtener datos secundarios (solo los esenciales para evitar rate limiting)
        // Comentamos la mayoría de requests secundarios para reducir carga
        const news = await Promise.resolve({ status: 'fulfilled' as const, value: [] as MarketNewsArticle[] }).catch(() => ({ status: 'fulfilled' as const, value: [] as MarketNewsArticle[] }));
        const events = await Promise.resolve({ status: 'fulfilled' as const, value: [] as CompanyEvent[] }).catch(() => ({ status: 'fulfilled' as const, value: [] as CompanyEvent[] }));
        const analystRecommendations = await Promise.resolve({ status: 'fulfilled' as const, value: null }).catch(() => ({ status: 'fulfilled' as const, value: null }));
        const targetPrice = await Promise.resolve({ status: 'fulfilled' as const, value: null }).catch(() => ({ status: 'fulfilled' as const, value: null }));
        const technicalAnalysis = await Promise.resolve({ status: 'fulfilled' as const, value: null }).catch(() => ({ status: 'fulfilled' as const, value: null }));
        const indexComparison = await Promise.resolve({ status: 'fulfilled' as const, value: null }).catch(() => ({ status: 'fulfilled' as const, value: null }));
        const insiderTrading = await Promise.resolve({ status: 'fulfilled' as const, value: null }).catch(() => ({ status: 'fulfilled' as const, value: null }));
        const peersData = await Promise.resolve({ status: 'fulfilled' as const, value: null as string[] | null }).catch(() => ({ status: 'fulfilled' as const, value: null as string[] | null }));

        // Procesar resultados
        const resolvedNews = news.status === 'fulfilled' ? news.value : [];
        const resolvedEvents = events.status === 'fulfilled' ? events.value : [];
        const resolvedAnalystRecs = analystRecommendations.status === 'fulfilled' ? analystRecommendations.value : null;
        const resolvedTargetPrice = targetPrice.status === 'fulfilled' ? targetPrice.value : null;
        const resolvedTechnical = technicalAnalysis.status === 'fulfilled' ? technicalAnalysis.value : null;
        const resolvedIndex = indexComparison.status === 'fulfilled' ? indexComparison.value : null;
        const resolvedInsider = insiderTrading.status === 'fulfilled' ? insiderTrading.value : null;
        const resolvedPeersData = peersData.status === 'fulfilled' ? peersData.value : null;

        // Si hay IPO date en el profile, agregarlo como evento
        if (profile?.ipo) {
            resolvedEvents.push({
                date: profile.ipo,
                event: 'IPO Date',
                description: `Initial Public Offering date`,
                importance: 'low',
            });
        }

        // Procesar peers
        let peers: string[] = [];
        if (Array.isArray(resolvedPeersData)) {
            peers = resolvedPeersData.filter(p => p && p !== symbol).slice(0, 10);
        }

        return { 
            quote, 
            profile, 
            metrics, 
            news: resolvedNews,
            events: resolvedEvents,
            analystRecommendations: resolvedAnalystRecs || resolvedTargetPrice,
            peers,
            technicalAnalysis: resolvedTechnical,
            indexComparison: resolvedIndex,
            insiderTrading: resolvedInsider,
            esgData: null, // Placeholder para futuras implementaciones
        };
    } catch (error) {
        console.error('Error fetching financial data for', symbol, error);
        return null;
    }
}

export const searchStocks = cache(async (query?: string): Promise<StockWithWatchlistStatus[]> => {
    try {
        const token = process.env.FINNHUB_API_KEY ?? NEXT_PUBLIC_FINNHUB_API_KEY;
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
                        console.error('Error fetching profile2 for', sym, e);
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

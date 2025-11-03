/**
 * Múltiples fuentes de datos de mercado
 * Sistema de fallback para cuando una API falla o se queda corta
 */

'use server';

// ========== FUENTES DE DATOS DISPONIBLES ==========

export enum DataSource {
    FINNHUB = 'finnhub',
    ALPHA_VANTAGE = 'alpha_vantage',
    POLYGON = 'polygon',
    YAHOO_FINANCE = 'yahoo_finance',
    TWELVE_DATA = 'twelve_data',
}

export interface QuoteData {
    symbol: string;
    currentPrice: number;
    previousClose?: number;
    change?: number;
    changePercent?: number;
    high?: number;
    low?: number;
    open?: number;
    volume?: number;
    timestamp?: number;
    source: DataSource;
}

export interface CompanyProfile {
    symbol: string;
    name: string;
    description?: string;
    sector?: string;
    industry?: string;
    exchange?: string;
    marketCap?: number;
    website?: string;
    logo?: string;
    country?: string;
    source: DataSource;
}

// ========== ALPHA VANTAGE ==========

/**
 * Obtiene cotización de Alpha Vantage (gratis hasta 5 llamadas/min, 500/día)
 * Mejorado con mejor manejo de errores, validación y timeout
 */
async function getQuoteAlphaVantage(symbol: string): Promise<QuoteData | null> {
    try {
        const apiKey = process.env.ALPHA_VANTAGE_API_KEY;
        if (!apiKey) {
            console.warn('Alpha Vantage API key no configurada');
            return null;
        }

        const url = `https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=${symbol}&apikey=${apiKey}`;
        
        // Timeout de 10 segundos para evitar bloqueos
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);
        
        const response = await fetch(url, { 
            next: { revalidate: 60 },
            signal: controller.signal,
        });
        
        clearTimeout(timeoutId);

        if (!response.ok) {
            console.warn(`Alpha Vantage HTTP error for ${symbol}:`, response.status);
            return null;
        }

        const data = await response.json();

        // Verificar errores de API (rate limiting, invalid API key, etc.)
        if (data['Error Message']) {
            console.warn(`Alpha Vantage API error for ${symbol}:`, data['Error Message']);
            return null;
        }

        if (data['Note']) {
            // Rate limit alcanzado
            console.warn(`Alpha Vantage rate limit for ${symbol}`);
            return null;
        }

        const quote = data['Global Quote'];

        if (!quote || !quote['05. price']) {
            console.warn(`Alpha Vantage no data for ${symbol}`);
            return null;
        }

        const price = parseFloat(quote['05. price']);
        if (isNaN(price) || price <= 0) {
            console.warn(`Alpha Vantage invalid price for ${symbol}:`, quote['05. price']);
            return null;
        }

        const change = parseFloat(quote['09. change']) || 0;
        const changePercent = parseFloat(quote['10. change percent']?.replace('%', '').replace(',', '.')) || 0;
        const previousClose = parseFloat(quote['08. previous close']) || price - change;

        return {
            symbol: quote['01. symbol'] || symbol,
            currentPrice: price,
            previousClose,
            change,
            changePercent,
            high: quote['03. high'] ? parseFloat(quote['03. high']) : undefined,
            low: quote['04. low'] ? parseFloat(quote['04. low']) : undefined,
            open: quote['02. open'] ? parseFloat(quote['02. open']) : undefined,
            volume: quote['06. volume'] ? parseFloat(quote['06. volume']) : undefined,
            timestamp: Date.now(),
            source: DataSource.ALPHA_VANTAGE,
        };
    } catch (error: any) {
        if (error.name === 'AbortError') {
            console.warn(`Alpha Vantage timeout for ${symbol}`);
        } else {
            console.error(`Alpha Vantage error for ${symbol}:`, error);
        }
        return null;
    }
}

/**
 * Obtiene perfil de empresa de Alpha Vantage
 */
async function getProfileAlphaVantage(symbol: string): Promise<CompanyProfile | null> {
    try {
        const apiKey = process.env.ALPHA_VANTAGE_API_KEY;
        if (!apiKey) return null;

        const url = `https://www.alphavantage.co/query?function=OVERVIEW&symbol=${symbol}&apikey=${apiKey}`;
        const response = await fetch(url, { next: { revalidate: 3600 } });

        if (!response.ok) return null;

        const data = await response.json();

        if (!data || !data.Symbol) return null;

        return {
            symbol: data.Symbol,
            name: data.Name || symbol,
            description: data.Description || undefined,
            sector: data.Sector || undefined,
            industry: data.Industry || undefined,
            exchange: data.Exchange || undefined,
            marketCap: data.MarketCapitalization ? parseInt(data.MarketCapitalization) : undefined,
            country: data.Country || undefined,
            source: DataSource.ALPHA_VANTAGE,
        };
    } catch (error) {
        console.error(`Alpha Vantage profile error for ${symbol}:`, error);
        return null;
    }
}

// ========== YAHOO FINANCE (NO API KEY REQUERIDA) ==========

/**
 * Obtiene cotización de Yahoo Finance (gratis, sin API key, pero menos confiable)
 * Mejorado con múltiples endpoints y mejor manejo de errores
 */
async function getQuoteYahooFinance(symbol: string): Promise<QuoteData | null> {
    try {
        // Usar yfinance API no oficial o endpoint público
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?interval=1d&range=1d`;
        const response = await fetch(url, { 
            next: { revalidate: 60 },
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            },
        });

        if (!response.ok) {
            // Intentar endpoint alternativo
            try {
                const altUrl = `https://query2.finance.yahoo.com/v8/finance/chart/${symbol}?interval=1d&range=1d`;
                const altResponse = await fetch(altUrl, { 
                    next: { revalidate: 60 },
                    headers: {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    },
                });
                
                if (!altResponse.ok) return null;
                return parseYahooFinanceResponse(await altResponse.json(), symbol);
            } catch {
                return null;
            }
        }

        const data = await response.json();
        return parseYahooFinanceResponse(data, symbol);
    } catch (error) {
        console.error(`Yahoo Finance error for ${symbol}:`, error);
        return null;
    }
}

/**
 * Parsea la respuesta de Yahoo Finance
 */
function parseYahooFinanceResponse(data: any, symbol: string): QuoteData | null {
    try {
        const result = data.chart?.result?.[0];

        if (!result || !result.meta) return null;

        const meta = result.meta;
        const price = meta.regularMarketPrice || meta.previousClose || meta.chartPreviousClose;

        if (!price || price <= 0) return null;

        const previousClose = meta.previousClose || meta.chartPreviousClose || price;
        const change = price - previousClose;
        const changePercent = previousClose > 0 ? (change / previousClose) * 100 : 0;

        return {
            symbol: meta.symbol || symbol,
            currentPrice: price,
            previousClose,
            change,
            changePercent,
            high: meta.regularMarketDayHigh || meta.chartPreviousClose,
            low: meta.regularMarketDayLow || meta.chartPreviousClose,
            open: meta.regularMarketOpen || meta.regularMarketPrice,
            volume: meta.regularMarketVolume,
            timestamp: meta.regularMarketTime ? meta.regularMarketTime * 1000 : Date.now(),
            source: DataSource.YAHOO_FINANCE,
        };
    } catch (error) {
        console.error('Error parsing Yahoo Finance response:', error);
        return null;
    }
}

// ========== POLYGON.IO ==========

/**
 * Obtiene cotización de Polygon.io (gratis con límites)
 */
async function getQuotePolygon(symbol: string): Promise<QuoteData | null> {
    try {
        const apiKey = process.env.POLYGON_API_KEY;
        if (!apiKey) return null;

        const url = `https://api.polygon.io/v2/aggs/ticker/${symbol}/prev?adjusted=true&apikey=${apiKey}`;
        const response = await fetch(url, { next: { revalidate: 60 } });

        if (!response.ok) return null;

        const data = await response.json();

        if (!data || !data.results || data.results.length === 0) return null;

        const result = data.results[0];
        const price = result.c; // Close price
        const previousClose = result.o; // Open price

        if (!price) return null;

        const change = price - previousClose;
        const changePercent = (change / previousClose) * 100;

        return {
            symbol: symbol,
            currentPrice: price,
            previousClose,
            change,
            changePercent,
            high: result.h || undefined,
            low: result.l || undefined,
            open: result.o || undefined,
            volume: result.v || undefined,
            timestamp: result.t || Date.now(),
            source: DataSource.POLYGON,
        };
    } catch (error) {
        console.error(`Polygon error for ${symbol}:`, error);
        return null;
    }
}

// ========== SISTEMA DE FALLBACK ==========

/**
 * Obtiene cotización con fallback automático a múltiples fuentes
 */
export async function getQuoteWithFallback(symbol: string): Promise<QuoteData | null> {
    // Orden de prioridad:
    // 1. Finnhub (si está disponible)
    // 2. Alpha Vantage
    // 3. Polygon
    // 4. Yahoo Finance (último recurso)

    // Intentar Finnhub primero (si está configurado)
    if (process.env.FINNHUB_API_KEY) {
        try {
            const finnhubUrl = `https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${process.env.FINNHUB_API_KEY}`;
            const response = await fetch(finnhubUrl, { next: { revalidate: 60 } });

            if (response.ok) {
                const data = await response.json();
                if (data.c && data.c > 0) {
                    return {
                        symbol,
                        currentPrice: data.c,
                        previousClose: data.pc,
                        change: data.d,
                        changePercent: data.dp,
                        high: data.h,
                        low: data.l,
                        open: data.o,
                        timestamp: data.t * 1000,
                        source: DataSource.FINNHUB,
                    };
                }
            }
        } catch (error) {
            console.warn(`Finnhub fallback for ${symbol}:`, error);
        }
    }

    // Intentar Alpha Vantage
    const alphaQuote = await getQuoteAlphaVantage(symbol);
    if (alphaQuote) return alphaQuote;

    // Intentar Polygon
    const polygonQuote = await getQuotePolygon(symbol);
    if (polygonQuote) return polygonQuote;

    // Último recurso: Yahoo Finance
    const yahooQuote = await getQuoteYahooFinance(symbol);
    if (yahooQuote) return yahooQuote;

    return null;
}

/**
 * Obtiene perfil de empresa con fallback
 */
export async function getProfileWithFallback(symbol: string): Promise<CompanyProfile | null> {
    // Intentar Finnhub primero
    if (process.env.FINNHUB_API_KEY) {
        try {
            const finnhubUrl = `https://finnhub.io/api/v1/stock/profile2?symbol=${symbol}&token=${process.env.FINNHUB_API_KEY}`;
            const response = await fetch(finnhubUrl, { next: { revalidate: 3600 } });

            if (response.ok) {
                const data = await response.json();
                if (data.name) {
                    return {
                        symbol: data.ticker || symbol,
                        name: data.name,
                        description: data.description,
                        sector: data.finnhubIndustry || data.industry,
                        industry: data.industry,
                        exchange: data.exchange,
                        marketCap: data.marketCapitalization,
                        website: data.weburl,
                        logo: data.logo,
                        country: data.country,
                        source: DataSource.FINNHUB,
                    };
                }
            }
        } catch (error) {
            console.warn(`Finnhub profile fallback for ${symbol}:`, error);
        }
    }

    // Intentar Alpha Vantage
    const alphaProfile = await getProfileAlphaVantage(symbol);
    if (alphaProfile) return alphaProfile;

    return null;
}







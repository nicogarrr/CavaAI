'use server';

import { cache } from 'react';
import { env } from '@/lib/env';

const TWELVE_DATA_BASE_URL = 'https://api.twelvedata.com';

/**
 * Helper function for TwelveData API calls
 */
async function fetchTwelveData<T>(endpoint: string, params: Record<string, string>): Promise<T | null> {
    const apiKey = env.TWELVE_DATA_API_KEY;
    if (!apiKey) {
        console.warn('TWELVE_DATA_API_KEY not configured');
        return null;
    }

    const queryParams = new URLSearchParams({
        ...params,
        apikey: apiKey,
    });

    const url = `${TWELVE_DATA_BASE_URL}${endpoint}?${queryParams.toString()}`;

    try {
        const response = await fetch(url, {
            next: { revalidate: 1800 }, // Cache 30 min
        });

        if (!response.ok) {
            console.error('TwelveData API error:', response.status);
            return null;
        }

        const data = await response.json();

        // TwelveData returns errors in status field
        if (data.status === 'error') {
            console.warn('TwelveData error:', data.message);
            return null;
        }

        return data as T;
    } catch (error) {
        console.error('Error fetching from TwelveData:', error);
        return null;
    }
}

// ============================================================================
// TECHNICAL INDICATORS
// ============================================================================

export type TechnicalIndicatorValue = {
    datetime: string;
    value: number;
};

export type TechnicalIndicatorResponse = {
    symbol: string;
    indicator: string;
    values: TechnicalIndicatorValue[];
};

/**
 * Get RSI (Relative Strength Index)
 */
export const getRSI = cache(async (
    symbol: string,
    interval: '1min' | '5min' | '15min' | '1h' | '4h' | '1day' | '1week' = '1day',
    timePeriod: number = 14,
    outputSize: number = 30
): Promise<TechnicalIndicatorResponse | null> => {
    const data = await fetchTwelveData<any>('/rsi', {
        symbol,
        interval,
        time_period: timePeriod.toString(),
        outputsize: outputSize.toString(),
    });

    if (!data || !data.values) {
        return null;
    }

    return {
        symbol,
        indicator: 'RSI',
        values: data.values.map((v: any) => ({
            datetime: v.datetime || '',
            value: parseFloat(v.rsi) || 0,
        })),
    };
});

/**
 * Get SMA (Simple Moving Average)
 */
export const getSMA = cache(async (
    symbol: string,
    interval: '1min' | '5min' | '15min' | '1h' | '4h' | '1day' | '1week' = '1day',
    timePeriod: number = 20,
    outputSize: number = 30
): Promise<TechnicalIndicatorResponse | null> => {
    const data = await fetchTwelveData<any>('/sma', {
        symbol,
        interval,
        time_period: timePeriod.toString(),
        outputsize: outputSize.toString(),
    });

    if (!data || !data.values) {
        return null;
    }

    return {
        symbol,
        indicator: `SMA(${timePeriod})`,
        values: data.values.map((v: any) => ({
            datetime: v.datetime || '',
            value: parseFloat(v.sma) || 0,
        })),
    };
});

/**
 * Get EMA (Exponential Moving Average)
 */
export const getEMA = cache(async (
    symbol: string,
    interval: '1min' | '5min' | '15min' | '1h' | '4h' | '1day' | '1week' = '1day',
    timePeriod: number = 20,
    outputSize: number = 30
): Promise<TechnicalIndicatorResponse | null> => {
    const data = await fetchTwelveData<any>('/ema', {
        symbol,
        interval,
        time_period: timePeriod.toString(),
        outputsize: outputSize.toString(),
    });

    if (!data || !data.values) {
        return null;
    }

    return {
        symbol,
        indicator: `EMA(${timePeriod})`,
        values: data.values.map((v: any) => ({
            datetime: v.datetime || '',
            value: parseFloat(v.ema) || 0,
        })),
    };
});

/**
 * Get MACD (Moving Average Convergence Divergence)
 */
export const getMACD = cache(async (
    symbol: string,
    interval: '1min' | '5min' | '15min' | '1h' | '4h' | '1day' | '1week' = '1day',
    outputSize: number = 30
): Promise<{
    symbol: string;
    indicator: string;
    values: Array<{
        datetime: string;
        macd: number;
        signal: number;
        histogram: number;
    }>;
} | null> => {
    const data = await fetchTwelveData<any>('/macd', {
        symbol,
        interval,
        outputsize: outputSize.toString(),
    });

    if (!data || !data.values) {
        return null;
    }

    return {
        symbol,
        indicator: 'MACD',
        values: data.values.map((v: any) => ({
            datetime: v.datetime || '',
            macd: parseFloat(v.macd) || 0,
            signal: parseFloat(v.macd_signal) || 0,
            histogram: parseFloat(v.macd_hist) || 0,
        })),
    };
});

/**
 * Get Bollinger Bands
 */
export const getBollingerBands = cache(async (
    symbol: string,
    interval: '1min' | '5min' | '15min' | '1h' | '4h' | '1day' | '1week' = '1day',
    timePeriod: number = 20,
    outputSize: number = 30
): Promise<{
    symbol: string;
    indicator: string;
    values: Array<{
        datetime: string;
        upper: number;
        middle: number;
        lower: number;
    }>;
} | null> => {
    const data = await fetchTwelveData<any>('/bbands', {
        symbol,
        interval,
        time_period: timePeriod.toString(),
        outputsize: outputSize.toString(),
    });

    if (!data || !data.values) {
        return null;
    }

    return {
        symbol,
        indicator: 'Bollinger Bands',
        values: data.values.map((v: any) => ({
            datetime: v.datetime || '',
            upper: parseFloat(v.upper_band) || 0,
            middle: parseFloat(v.middle_band) || 0,
            lower: parseFloat(v.lower_band) || 0,
        })),
    };
});

/**
 * Get Stochastic Oscillator
 */
export const getStochastic = cache(async (
    symbol: string,
    interval: '1min' | '5min' | '15min' | '1h' | '4h' | '1day' | '1week' = '1day',
    outputSize: number = 30
): Promise<{
    symbol: string;
    indicator: string;
    values: Array<{
        datetime: string;
        slowK: number;
        slowD: number;
    }>;
} | null> => {
    const data = await fetchTwelveData<any>('/stoch', {
        symbol,
        interval,
        outputsize: outputSize.toString(),
    });

    if (!data || !data.values) {
        return null;
    }

    return {
        symbol,
        indicator: 'Stochastic',
        values: data.values.map((v: any) => ({
            datetime: v.datetime || '',
            slowK: parseFloat(v.slow_k) || 0,
            slowD: parseFloat(v.slow_d) || 0,
        })),
    };
});

/**
 * Get ADX (Average Directional Index)
 */
export const getADX = cache(async (
    symbol: string,
    interval: '1min' | '5min' | '15min' | '1h' | '4h' | '1day' | '1week' = '1day',
    timePeriod: number = 14,
    outputSize: number = 30
): Promise<TechnicalIndicatorResponse | null> => {
    const data = await fetchTwelveData<any>('/adx', {
        symbol,
        interval,
        time_period: timePeriod.toString(),
        outputsize: outputSize.toString(),
    });

    if (!data || !data.values) {
        return null;
    }

    return {
        symbol,
        indicator: 'ADX',
        values: data.values.map((v: any) => ({
            datetime: v.datetime || '',
            value: parseFloat(v.adx) || 0,
        })),
    };
});

/**
 * Get ATR (Average True Range)
 */
export const getATR = cache(async (
    symbol: string,
    interval: '1min' | '5min' | '15min' | '1h' | '4h' | '1day' | '1week' = '1day',
    timePeriod: number = 14,
    outputSize: number = 30
): Promise<TechnicalIndicatorResponse | null> => {
    const data = await fetchTwelveData<any>('/atr', {
        symbol,
        interval,
        time_period: timePeriod.toString(),
        outputsize: outputSize.toString(),
    });

    if (!data || !data.values) {
        return null;
    }

    return {
        symbol,
        indicator: 'ATR',
        values: data.values.map((v: any) => ({
            datetime: v.datetime || '',
            value: parseFloat(v.atr) || 0,
        })),
    };
});

/**
 * Get all key technical indicators at once
 */
export async function getAllTechnicalIndicators(symbol: string, interval: '1day' | '1week' = '1day'): Promise<{
    rsi: TechnicalIndicatorResponse | null;
    sma20: TechnicalIndicatorResponse | null;
    sma50: TechnicalIndicatorResponse | null;
    ema12: TechnicalIndicatorResponse | null;
    ema26: TechnicalIndicatorResponse | null;
    macd: any;
    bollingerBands: any;
    stochastic: any;
    adx: TechnicalIndicatorResponse | null;
    atr: TechnicalIndicatorResponse | null;
}> {
    const [rsi, sma20, sma50, ema12, ema26, macd, bollingerBands, stochastic, adx, atr] = await Promise.all([
        getRSI(symbol, interval, 14, 10),
        getSMA(symbol, interval, 20, 10),
        getSMA(symbol, interval, 50, 10),
        getEMA(symbol, interval, 12, 10),
        getEMA(symbol, interval, 26, 10),
        getMACD(symbol, interval, 10),
        getBollingerBands(symbol, interval, 20, 10),
        getStochastic(symbol, interval, 10),
        getADX(symbol, interval, 14, 10),
        getATR(symbol, interval, 14, 10),
    ]);

    return {
        rsi,
        sma20,
        sma50,
        ema12,
        ema26,
        macd,
        bollingerBands,
        stochastic,
        adx,
        atr,
    };
}

// ============================================================================
// ETF DATA
// ============================================================================

export type ETFProfile = {
    symbol: string;
    name: string;
    exchange: string;
    currency: string;
    country: string;
    type: string;
};

export type ETFHolding = {
    symbol: string;
    name: string;
    weight: number;
    shares: number;
};

/**
 * Get ETF Profile
 */
export const getETFProfile = cache(async (symbol: string): Promise<ETFProfile | null> => {
    const data = await fetchTwelveData<any>('/etf', {
        symbol,
    });

    if (!data || data.status === 'error') {
        return null;
    }

    return {
        symbol: data.symbol || symbol,
        name: data.name || '',
        exchange: data.exchange || '',
        currency: data.currency || 'USD',
        country: data.country || 'US',
        type: data.type || 'ETF',
    };
});

// ============================================================================
// MUTUAL FUND DATA
// ============================================================================

export type MutualFundProfile = {
    symbol: string;
    name: string;
    exchange: string;
    currency: string;
    fundFamily: string;
    fundType: string;
};

/**
 * Get Mutual Fund Profile
 */
export const getMutualFundProfile = cache(async (symbol: string): Promise<MutualFundProfile | null> => {
    const data = await fetchTwelveData<any>('/mutual_funds', {
        symbol,
    });

    if (!data || data.status === 'error') {
        return null;
    }

    return {
        symbol: data.symbol || symbol,
        name: data.name || '',
        exchange: data.exchange || '',
        currency: data.currency || 'USD',
        fundFamily: data.fund_family || '',
        fundType: data.fund_type || '',
    };
});

// ============================================================================
// ADDITIONAL DATA
// ============================================================================

/**
 * Get Statistics (key metrics)
 */
export const getStatistics = cache(async (symbol: string): Promise<{
    symbol: string;
    fiftyTwoWeekHigh: number;
    fiftyTwoWeekLow: number;
    marketCap: number;
    sharesOutstanding: number;
    beta: number;
    peRatio: number;
    eps: number;
    dividendYield: number;
} | null> => {
    const data = await fetchTwelveData<any>('/statistics', {
        symbol,
    });

    if (!data || !data.statistics) {
        return null;
    }

    const stats = data.statistics;
    return {
        symbol,
        fiftyTwoWeekHigh: parseFloat(stats['52_week_high']) || 0,
        fiftyTwoWeekLow: parseFloat(stats['52_week_low']) || 0,
        marketCap: parseFloat(stats.market_capitalization) || 0,
        sharesOutstanding: parseFloat(stats.shares_outstanding) || 0,
        beta: parseFloat(stats.beta) || 0,
        peRatio: parseFloat(stats.pe_ratio) || 0,
        eps: parseFloat(stats.eps) || 0,
        dividendYield: parseFloat(stats.dividend_yield) || 0,
    };
});

/**
 * Get Earnings
 */
export const getEarnings = cache(async (symbol: string): Promise<Array<{
    date: string;
    time: string;
    epsEstimate: number;
    epsActual: number;
    difference: number;
    surprisePercent: number;
}> | null> => {
    const data = await fetchTwelveData<any>('/earnings', {
        symbol,
    });

    if (!data || !data.earnings) {
        return null;
    }

    return data.earnings.slice(0, 8).map((e: any) => ({
        date: e.date || '',
        time: e.time || '',
        epsEstimate: parseFloat(e.eps_estimate) || 0,
        epsActual: parseFloat(e.eps_actual) || 0,
        difference: parseFloat(e.difference) || 0,
        surprisePercent: parseFloat(e.surprise_prc) || 0,
    }));
});

/**
 * Get Recommendations (analyst ratings)
 */
export const getRecommendations = cache(async (symbol: string): Promise<{
    symbol: string;
    strongBuy: number;
    buy: number;
    hold: number;
    sell: number;
    strongSell: number;
    period: string;
} | null> => {
    const data = await fetchTwelveData<any>('/recommendations', {
        symbol,
    });

    if (!data || !Array.isArray(data) || data.length === 0) {
        return null;
    }

    const latest = data[0];
    return {
        symbol,
        strongBuy: latest.strong_buy || 0,
        buy: latest.buy || 0,
        hold: latest.hold || 0,
        sell: latest.sell || 0,
        strongSell: latest.strong_sell || 0,
        period: latest.period || '',
    };
});

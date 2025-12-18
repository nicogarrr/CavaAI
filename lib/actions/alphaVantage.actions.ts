'use server';

import { cache } from 'react';
import { env } from '@/lib/env';

const ALPHA_VANTAGE_BASE_URL = 'https://www.alphavantage.co/query';

/**
 * Helper function for Alpha Vantage API calls
 */
async function fetchAlphaVantage<T>(params: Record<string, string>): Promise<T | null> {
    const apiKey = env.ALPHA_VANTAGE_API_KEY;
    if (!apiKey) {
        console.warn('ALPHA_VANTAGE_API_KEY not configured');
        return null;
    }

    const queryParams = new URLSearchParams({
        ...params,
        apikey: apiKey,
    });

    const url = `${ALPHA_VANTAGE_BASE_URL}?${queryParams.toString()}`;

    try {
        const response = await fetch(url, {
            next: { revalidate: 3600 }, // Cache 1 hour
        });

        if (!response.ok) {
            console.error('Alpha Vantage API error:', response.status);
            return null;
        }

        const data = await response.json();

        // Alpha Vantage returns error messages in the response body
        if (data['Error Message'] || data['Note']) {
            console.warn('Alpha Vantage warning:', data['Error Message'] || data['Note']);
            return null;
        }

        return data as T;
    } catch (error) {
        console.error('Error fetching from Alpha Vantage:', error);
        return null;
    }
}

// ============================================================================
// NEWS SENTIMENT
// ============================================================================

export type NewsSentimentItem = {
    title: string;
    url: string;
    timePublished: string;
    summary: string;
    source: string;
    overallSentimentScore: number;
    overallSentimentLabel: 'Bullish' | 'Somewhat-Bullish' | 'Neutral' | 'Somewhat-Bearish' | 'Bearish';
    tickerSentiment: Array<{
        ticker: string;
        relevanceScore: number;
        sentimentScore: number;
        sentimentLabel: string;
    }>;
};

export type NewsSentimentResponse = {
    items: NewsSentimentItem[];
    sentimentScoreAverage: number;
    relevantArticles: number;
};

export const getNewsSentiment = cache(async (
    tickers?: string,
    topics?: string,
    limit: number = 50
): Promise<NewsSentimentResponse | null> => {
    const params: Record<string, string> = {
        function: 'NEWS_SENTIMENT',
        limit: limit.toString(),
    };

    if (tickers) params.tickers = tickers;
    if (topics) params.topics = topics;

    const data = await fetchAlphaVantage<any>(params);

    if (!data || !data.feed) {
        return null;
    }

    const items: NewsSentimentItem[] = data.feed.map((item: any) => ({
        title: item.title || '',
        url: item.url || '',
        timePublished: item.time_published || '',
        summary: item.summary || '',
        source: item.source || '',
        overallSentimentScore: parseFloat(item.overall_sentiment_score) || 0,
        overallSentimentLabel: item.overall_sentiment_label || 'Neutral',
        tickerSentiment: (item.ticker_sentiment || []).map((t: any) => ({
            ticker: t.ticker || '',
            relevanceScore: parseFloat(t.relevance_score) || 0,
            sentimentScore: parseFloat(t.ticker_sentiment_score) || 0,
            sentimentLabel: t.ticker_sentiment_label || 'Neutral',
        })),
    }));

    // Calculate average sentiment
    const sentimentScoreAverage = items.length > 0
        ? items.reduce((sum, item) => sum + item.overallSentimentScore, 0) / items.length
        : 0;

    return {
        items: items.slice(0, limit),
        sentimentScoreAverage,
        relevantArticles: data.items || items.length,
    };
});

// ============================================================================
// ECONOMIC INDICATORS
// ============================================================================

export type EconomicDataPoint = {
    date: string;
    value: number;
};

export type EconomicIndicator = {
    name: string;
    interval: string;
    unit: string;
    data: EconomicDataPoint[];
};

/**
 * Fetch Real GDP data
 */
export const getRealGDP = cache(async (interval: 'annual' | 'quarterly' = 'quarterly'): Promise<EconomicIndicator | null> => {
    const data = await fetchAlphaVantage<any>({
        function: 'REAL_GDP',
        interval,
    });

    if (!data || !data.data) {
        return null;
    }

    return {
        name: 'Real GDP',
        interval: data.interval || interval,
        unit: data.unit || 'billions of dollars',
        data: data.data.slice(0, 20).map((d: any) => ({
            date: d.date || '',
            value: parseFloat(d.value) || 0,
        })),
    };
});

/**
 * Fetch CPI (Inflation) data
 */
export const getCPI = cache(async (interval: 'monthly' | 'semiannual' = 'monthly'): Promise<EconomicIndicator | null> => {
    const data = await fetchAlphaVantage<any>({
        function: 'CPI',
        interval,
    });

    if (!data || !data.data) {
        return null;
    }

    return {
        name: 'Consumer Price Index',
        interval: data.interval || interval,
        unit: data.unit || 'index',
        data: data.data.slice(0, 24).map((d: any) => ({
            date: d.date || '',
            value: parseFloat(d.value) || 0,
        })),
    };
});

/**
 * Fetch Unemployment Rate
 */
export const getUnemploymentRate = cache(async (): Promise<EconomicIndicator | null> => {
    const data = await fetchAlphaVantage<any>({
        function: 'UNEMPLOYMENT',
    });

    if (!data || !data.data) {
        return null;
    }

    return {
        name: 'Unemployment Rate',
        interval: 'monthly',
        unit: 'percent',
        data: data.data.slice(0, 24).map((d: any) => ({
            date: d.date || '',
            value: parseFloat(d.value) || 0,
        })),
    };
});

/**
 * Fetch Federal Funds Rate
 */
export const getFederalFundsRate = cache(async (interval: 'daily' | 'weekly' | 'monthly' = 'monthly'): Promise<EconomicIndicator | null> => {
    const data = await fetchAlphaVantage<any>({
        function: 'FEDERAL_FUNDS_RATE',
        interval,
    });

    if (!data || !data.data) {
        return null;
    }

    return {
        name: 'Federal Funds Rate',
        interval: data.interval || interval,
        unit: 'percent',
        data: data.data.slice(0, 24).map((d: any) => ({
            date: d.date || '',
            value: parseFloat(d.value) || 0,
        })),
    };
});

/**
 * Fetch Treasury Yield
 */
export const getTreasuryYield = cache(async (
    maturity: '3month' | '2year' | '5year' | '7year' | '10year' | '30year' = '10year',
    interval: 'daily' | 'weekly' | 'monthly' = 'monthly'
): Promise<EconomicIndicator | null> => {
    const data = await fetchAlphaVantage<any>({
        function: 'TREASURY_YIELD',
        interval,
        maturity,
    });

    if (!data || !data.data) {
        return null;
    }

    return {
        name: `Treasury Yield (${maturity})`,
        interval: data.interval || interval,
        unit: 'percent',
        data: data.data.slice(0, 24).map((d: any) => ({
            date: d.date || '',
            value: parseFloat(d.value) || 0,
        })),
    };
});

/**
 * Fetch Inflation Rate
 */
export const getInflation = cache(async (): Promise<EconomicIndicator | null> => {
    const data = await fetchAlphaVantage<any>({
        function: 'INFLATION',
    });

    if (!data || !data.data) {
        return null;
    }

    return {
        name: 'Annual Inflation Rate',
        interval: 'annual',
        unit: 'percent',
        data: data.data.slice(0, 10).map((d: any) => ({
            date: d.date || '',
            value: parseFloat(d.value) || 0,
        })),
    };
});

/**
 * Get all key economic indicators at once
 */
export async function getAllEconomicIndicators(): Promise<{
    gdp: EconomicIndicator | null;
    cpi: EconomicIndicator | null;
    unemployment: EconomicIndicator | null;
    federalFundsRate: EconomicIndicator | null;
    treasuryYield10Y: EconomicIndicator | null;
    inflation: EconomicIndicator | null;
}> {
    const [gdp, cpi, unemployment, federalFundsRate, treasuryYield10Y, inflation] = await Promise.all([
        getRealGDP('quarterly'),
        getCPI('monthly'),
        getUnemploymentRate(),
        getFederalFundsRate('monthly'),
        getTreasuryYield('10year', 'monthly'),
        getInflation(),
    ]);

    return {
        gdp,
        cpi,
        unemployment,
        federalFundsRate,
        treasuryYield10Y,
        inflation,
    };
}

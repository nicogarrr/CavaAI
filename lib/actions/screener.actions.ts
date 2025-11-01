'use server';

import { cache } from 'react';

const FINNHUB_BASE_URL = 'https://finnhub.io/api/v1';
const FINNHUB_API_KEY = process.env.FINNHUB_API_KEY ?? process.env.NEXT_PUBLIC_FINNHUB_API_KEY;

export type ScreenerFilters = {
  marketCapMin: number;
  marketCapMax: number;
  priceMin: number;
  priceMax: number;
  peMin: number;
  peMax: number;
  pbMin: number;
  pbMax: number;
  roeMin: number;
  roeMax: number;
  volumeMin: number;
  betaMin: number;
  betaMax: number;
  sector: string;
  exchange: string;
  assetType: string;
  sortBy: string;
  sortOrder: 'asc' | 'desc';
};

export type ScreenerResult = {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  marketCap: number;
  pe: number;
  pb: number;
  roe: number;
  volume: number;
  beta: number;
  sector: string;
  exchange: string;
  type: string;
};

// Lista de símbolos populares para screener (expandible)
const POPULAR_SYMBOLS = [
  'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'BRK.B', 'JNJ', 'V',
  'WMT', 'JPM', 'PG', 'MA', 'UNH', 'HD', 'DIS', 'PYPL', 'NFLX', 'ADBE',
  'CRM', 'CSCO', 'PFE', 'INTC', 'VZ', 'T', 'KO', 'PEP', 'MRK', 'ABT',
  // ETFs
  'SPY', 'QQQ', 'IWM', 'DIA', 'VOO', 'VTI', 'URTH', 'VWO', 'GLD', 'BITO',
];

async function fetchWithTimeout(url: string, timeout = 5000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  
  try {
    const response = await fetch(url, { signal: controller.signal });
    clearTimeout(id);
    return response;
  } catch (error) {
    clearTimeout(id);
    throw error;
  }
}

export const screenStocks = cache(async (filters: ScreenerFilters): Promise<ScreenerResult[]> => {
  if (!FINNHUB_API_KEY) {
    console.error('Finnhub API key not configured');
    return [];
  }

  try {
    const results: ScreenerResult[] = [];
    
    // Fetch data for each symbol in parallel
    const promises = POPULAR_SYMBOLS.map(async (symbol) => {
      try {
        // Get quote data
        const quoteUrl = `${FINNHUB_BASE_URL}/quote?symbol=${symbol}&token=${FINNHUB_API_KEY}`;
        const quoteRes = await fetchWithTimeout(quoteUrl);
        
        if (!quoteRes.ok) return null;
        
        const quote = await quoteRes.json();
        
        if (!quote.c || quote.c === 0) return null;
        
        // Get company profile
        const profileUrl = `${FINNHUB_BASE_URL}/stock/profile2?symbol=${symbol}&token=${FINNHUB_API_KEY}`;
        const profileRes = await fetchWithTimeout(profileUrl);
        
        if (!profileRes.ok) return null;
        
        const profile = await profileRes.json();
        
        // Get basic financials (includes PE, PB, etc.)
        const metricsUrl = `${FINNHUB_BASE_URL}/stock/metric?symbol=${symbol}&metric=all&token=${FINNHUB_API_KEY}`;
        const metricsRes = await fetchWithTimeout(metricsUrl);
        
        let metrics: any = { metric: {} };
        if (metricsRes.ok) {
          metrics = await metricsRes.json();
        }
        
        const price = quote.c || 0;
        const change = quote.d || 0;
        const changePercent = quote.dp || 0;
        
        const result: ScreenerResult = {
          symbol,
          name: profile.name || symbol,
          price,
          change,
          changePercent,
          marketCap: profile.marketCapitalization ? profile.marketCapitalization * 1000000 : 0,
          pe: (metrics.metric as any)?.peBasicExclExtraTTM || 0,
          pb: (metrics.metric as any)?.pbAnnual || 0,
          roe: (metrics.metric as any)?.roeTTM || 0,
          volume: quote.v || 0,
          beta: (metrics.metric as any)?.beta || 1.0,
          sector: profile.finnhubIndustry || 'Unknown',
          exchange: profile.exchange || 'US',
          type: symbol.match(/^[A-Z]{3,4}$/) && ['SPY', 'QQQ', 'IWM', 'VOO', 'VTI', 'URTH', 'VWO', 'GLD', 'BITO'].includes(symbol) ? 'ETF' : 'Stock',
        };
        
        // Apply filters
        if (result.price < filters.priceMin || result.price > filters.priceMax) return null;
        if (result.marketCap < filters.marketCapMin || result.marketCap > filters.marketCapMax) return null;
        if (result.pe > 0 && (result.pe < filters.peMin || result.pe > filters.peMax)) return null;
        if (result.pb > 0 && (result.pb < filters.pbMin || result.pb > filters.pbMax)) return null;
        if (result.roe > 0 && (result.roe < filters.roeMin || result.roe > filters.roeMax)) return null;
        if (result.volume < filters.volumeMin) return null;
        if (result.beta < filters.betaMin || result.beta > filters.betaMax) return null;
        
        if (filters.sector !== 'all' && result.sector !== filters.sector) return null;
        if (filters.exchange !== 'all' && result.exchange !== filters.exchange) return null;
        if (filters.assetType !== 'all' && result.type !== filters.assetType) return null;
        
        return result;
      } catch (error) {
        console.error(`Error fetching data for ${symbol}:`, error);
        return null;
      }
    });
    
    const settled = await Promise.allSettled(promises);
    
    for (const result of settled) {
      if (result.status === 'fulfilled' && result.value) {
        results.push(result.value);
      }
    }
    
    // Sort results
    results.sort((a, b) => {
      const aVal = a[filters.sortBy as keyof ScreenerResult] as number;
      const bVal = b[filters.sortBy as keyof ScreenerResult] as number;
      
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return filters.sortOrder === 'asc' ? aVal - bVal : bVal - aVal;
      }
      
      return 0;
    });
    
    return results;
  } catch (error) {
    console.error('Error in screenStocks:', error);
    return [];
  }
});

export async function exportScreenerResults(results: ScreenerResult[]): Promise<string> {
  // Generate CSV
  const headers = [
    'Symbol', 'Name', 'Price', 'Change', 'Change %', 'Market Cap', 
    'P/E', 'P/B', 'ROE', 'Volume', 'Beta', 'Sector', 'Exchange', 'Type'
  ];
  
  const rows = results.map(r => [
    r.symbol,
    r.name,
    r.price.toFixed(2),
    r.change.toFixed(2),
    r.changePercent.toFixed(2),
    r.marketCap.toFixed(0),
    r.pe.toFixed(2),
    r.pb.toFixed(2),
    r.roe.toFixed(2),
    r.volume.toFixed(0),
    r.beta.toFixed(2),
    r.sector,
    r.exchange,
    r.type,
  ]);
  
  const csv = [
    headers.join(','),
    ...rows.map(row => row.join(','))
  ].join('\n');
  
  return csv;
}

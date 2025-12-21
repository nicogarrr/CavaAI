'use server';

import { cache } from 'react';

// Solo usar backend si está configurado explícitamente (no en Vercel)
const FMP_BACKEND_URL = process.env.FMP_BACKEND_URL;
const IS_SERVERLESS = process.env.VERCEL || !FMP_BACKEND_URL;

/**
 * Generic fetch helper for FMP backend
 * Returns null immediately in serverless environments (Vercel)
 */
async function fetchFromBackend<T>(endpoint: string): Promise<T | null> {
    // En Vercel/serverless, no hay backend Python disponible
    if (IS_SERVERLESS) {
        return null;
    }
    
    try {
        const response = await fetch(`${FMP_BACKEND_URL}${endpoint}`, {
            next: { revalidate: 3600 }, // Cache for 1 hour
        });

        if (!response.ok) {
            console.error(`FMP Backend error: ${response.status} for ${endpoint}`);
            return null;
        }

        return await response.json();
    } catch (error) {
        console.error(`FMP Backend fetch failed for ${endpoint}:`, error);
        return null;
    }
}

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

export interface IncomeStatement {
    date: string;
    symbol: string;
    revenue: number;
    grossProfit: number;
    operatingIncome: number;
    netIncome: number;
    eps: number;
    grossProfitRatio: number;
    operatingIncomeRatio: number;
    netIncomeRatio: number;
}

export interface BalanceSheet {
    date: string;
    symbol: string;
    totalAssets: number;
    totalLiabilities: number;
    totalStockholdersEquity: number;
    totalDebt: number;
    cashAndCashEquivalents: number;
    totalCurrentAssets: number;
    totalCurrentLiabilities: number;
}

export interface CashFlowStatement {
    date: string;
    symbol: string;
    operatingCashFlow: number;
    capitalExpenditure: number;
    freeCashFlow: number;
    dividendsPaid: number;
}

export interface FundamentalsData {
    symbol: string;
    period: string;
    income: IncomeStatement[];
    balance: BalanceSheet[];
    cashflow: CashFlowStatement[];
}

export interface GrowthData {
    date: string;
    revenueGrowth: number;
    netIncomeGrowth: number;
    epsgrowth: number;
    freeCashFlowGrowth: number;
    operatingCashFlowGrowth: number;
    grossProfitGrowth: number;
}

export interface RatiosTTM {
    peRatioTTM: number;
    pegRatioTTM: number;
    priceToSalesRatioTTM: number;
    priceToBookRatioTTM: number;
    returnOnEquityTTM: number;
    returnOnAssetsTTM: number;
    returnOnCapitalEmployedTTM: number;
    dividendYieldTTM: number;
    currentRatioTTM: number;
    quickRatioTTM: number;
    debtRatioTTM: number;
    debtEquityRatioTTM: number;
    grossProfitMarginTTM: number;
    operatingProfitMarginTTM: number;
    netProfitMarginTTM: number;
}

export interface DCFData {
    symbol: string;
    date: string;
    dcf: number;
    stockPrice: number;
}

export interface EnterpriseValueData {
    date: string;
    symbol: string;
    stockPrice: number;
    marketCapitalization: number;
    enterpriseValue: number;
    numberOfShares: number;
    minusCashAndCashEquivalents: number;
    addTotalDebt: number;
}

// ============================================================================
// SERVER ACTIONS
// ============================================================================

/**
 * Fetch combined financial statements (Income, Balance, CashFlow)
 */
export const getFundamentals = cache(async (symbol: string, period: string = 'annual'): Promise<FundamentalsData | null> => {
    const data = await fetchFromBackend<FundamentalsData>(`/fundamentals/${symbol}?period=${period}`);
    return data;
});

/**
 * Fetch pre-calculated growth metrics from FMP
 */
export const getFinancialGrowth = cache(async (symbol: string): Promise<{ symbol: string; growth: GrowthData[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; growth: GrowthData[] }>(`/financial-growth/${symbol}`);
    return data;
});

/**
 * Fetch financial data from Yahoo Finance (works on Vercel)
 */
async function getYahooFinancialData(symbol: string): Promise<{
    ratios: RatiosTTM | null;
    keyMetrics: KeyMetricsTTM | null;
}> {
    try {
        const url = `https://query1.finance.yahoo.com/v10/finance/quoteSummary/${encodeURIComponent(symbol)}?modules=financialData,defaultKeyStatistics,summaryDetail,price`;
        
        const response = await fetch(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            },
            next: { revalidate: 3600 }, // Cache 1 hour
        });
        
        if (!response.ok) {
            console.warn(`Yahoo Finance failed for ${symbol}: ${response.status}`);
            return { ratios: null, keyMetrics: null };
        }
        
        const data = await response.json();
        const result = data?.quoteSummary?.result?.[0];
        
        if (!result) {
            return { ratios: null, keyMetrics: null };
        }
        
        const financialData = result.financialData || {};
        const keyStats = result.defaultKeyStatistics || {};
        const summaryDetail = result.summaryDetail || {};
        const price = result.price || {};
        
        // Extract raw values safely
        const getValue = (obj: any) => obj?.raw ?? obj ?? null;
        
        const ratios: RatiosTTM = {
            peRatioTTM: getValue(summaryDetail.trailingPE) || getValue(keyStats.trailingPE),
            pegRatioTTM: getValue(keyStats.pegRatio),
            priceToSalesRatioTTM: getValue(summaryDetail.priceToSalesTrailing12Months),
            priceToBookRatioTTM: getValue(keyStats.priceToBook),
            returnOnEquityTTM: getValue(financialData.returnOnEquity),
            returnOnAssetsTTM: getValue(financialData.returnOnAssets),
            returnOnCapitalEmployedTTM: null as any,
            dividendYieldTTM: getValue(summaryDetail.dividendYield),
            currentRatioTTM: getValue(financialData.currentRatio),
            quickRatioTTM: getValue(financialData.quickRatio),
            debtRatioTTM: null as any,
            debtEquityRatioTTM: getValue(financialData.debtToEquity) ? getValue(financialData.debtToEquity) / 100 : null as any,
            grossProfitMarginTTM: getValue(financialData.grossMargins),
            operatingProfitMarginTTM: getValue(financialData.operatingMargins),
            netProfitMarginTTM: getValue(financialData.profitMargins),
        };
        
        const keyMetrics: KeyMetricsTTM = {
            marketCapTTM: getValue(price.marketCap),
            peRatioTTM: getValue(summaryDetail.trailingPE) || getValue(keyStats.trailingPE),
            priceToSalesRatioTTM: getValue(summaryDetail.priceToSalesTrailing12Months),
            pbRatioTTM: getValue(keyStats.priceToBook),
            enterpriseValueTTM: getValue(keyStats.enterpriseValue),
            enterpriseValueOverEBITDATTM: getValue(keyStats.enterpriseToEbitda),
            dividendYieldTTM: getValue(summaryDetail.dividendYield),
            currentRatioTTM: getValue(financialData.currentRatio),
            debtToEquityTTM: getValue(financialData.debtToEquity) ? getValue(financialData.debtToEquity) / 100 : null as any,
            roeTTM: getValue(financialData.returnOnEquity),
            netIncomePerShareTTM: getValue(keyStats.trailingEps)?.raw ?? getValue(summaryDetail.trailingEps),
            // Fill remaining with nulls
            revenuePerShareTTM: null as any,
            operatingCashFlowPerShareTTM: getValue(financialData.operatingCashflow) ? getValue(financialData.operatingCashflow) / getValue(price.sharesOutstanding) : null as any,
            freeCashFlowPerShareTTM: getValue(financialData.freeCashflow) ? getValue(financialData.freeCashflow) / getValue(price.sharesOutstanding) : null as any,
            cashPerShareTTM: getValue(financialData.totalCash) ? getValue(financialData.totalCash) / getValue(price.sharesOutstanding) : null as any,
            bookValuePerShareTTM: getValue(keyStats.bookValue),
            tangibleBookValuePerShareTTM: null as any,
            shareholdersEquityPerShareTTM: null as any,
            interestDebtPerShareTTM: null as any,
            pocfratioTTM: null as any,
            pfcfRatioTTM: null as any,
            ptbRatioTTM: getValue(keyStats.priceToBook),
            evToSalesTTM: getValue(keyStats.enterpriseToRevenue),
            evToOperatingCashFlowTTM: null as any,
            evToFreeCashFlowTTM: null as any,
            earningsYieldTTM: getValue(summaryDetail.trailingPE) ? 1 / getValue(summaryDetail.trailingPE) : null as any,
            freeCashFlowYieldTTM: null as any,
            debtToAssetsTTM: null as any,
            netDebtToEBITDATTM: null as any,
            interestCoverageTTM: null as any,
            incomeQualityTTM: null as any,
            payoutRatioTTM: getValue(summaryDetail.payoutRatio),
            salesGeneralAndAdministrativeToRevenueTTM: null as any,
            researchAndDevelopementToRevenueTTM: null as any,
            intangiblesToTotalAssetsTTM: null as any,
            capexToOperatingCashFlowTTM: null as any,
            capexToRevenueTTM: null as any,
            capexToDepreciationTTM: null as any,
            stockBasedCompensationToRevenueTTM: null as any,
            grahamNumberTTM: null as any,
            roicTTM: null as any,
            returnOnTangibleAssetsTTM: null as any,
            grahamNetNetTTM: null as any,
            workingCapitalTTM: null as any,
            tangibleAssetValueTTM: null as any,
            netCurrentAssetValueTTM: null as any,
            investedCapitalTTM: null as any,
            averageReceivablesTTM: null as any,
            averagePayablesTTM: null as any,
            averageInventoryTTM: null as any,
            daysSalesOutstandingTTM: null as any,
            daysPayablesOutstandingTTM: null as any,
            daysOfInventoryOnHandTTM: null as any,
            receivablesTurnoverTTM: null as any,
            payablesTurnoverTTM: null as any,
            inventoryTurnoverTTM: null as any,
            capexPerShareTTM: null as any,
        };
        
        return { ratios, keyMetrics };
        
    } catch (error) {
        console.error("Error fetching Yahoo Finance data:", error);
        return { ratios: null, keyMetrics: null };
    }
}

/**
 * Fetch TTM ratios (PER, ROIC, ROE, P/S, P/B)
 * Uses Yahoo Finance as primary source (works on Vercel)
 */
export const getRatiosTTM = cache(async (symbol: string): Promise<{ symbol: string; ratios: RatiosTTM[] } | null> => {
    // Try Yahoo Finance first (works on Vercel)
    const yahooData = await getYahooFinancialData(symbol);
    if (yahooData.ratios) {
        return { symbol, ratios: [yahooData.ratios] };
    }
    
    // Fallback to Python backend (only works locally)
    if (!IS_SERVERLESS) {
        const data = await fetchFromBackend<{ symbol: string; ratios: RatiosTTM[] }>(`/ratios-ttm/${symbol}`);
        return data;
    }
    
    return null;
});

/**
 * Fetch Discounted Cash Flow valuation (intrinsic value)
 */
export const getDCF = cache(async (symbol: string): Promise<{ symbol: string; dcf: DCFData[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; dcf: DCFData[] }>(`/dcf/${symbol}`);
    return data;
});

/**
 * Fetch Enterprise Value data (for EV/EBITDA, EV/FCF calculations)
 */
export const getEnterpriseValue = cache(async (symbol: string): Promise<{ symbol: string; enterpriseValue: EnterpriseValueData[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; enterpriseValue: EnterpriseValueData[] }>(`/enterprise-value/${symbol}`);
    return data;
});

/**
 * Get all valuation data in one call (optimized for component)
 */
export const getValuationData = cache(async (symbol: string) => {
    const [ratios, dcf, ev] = await Promise.all([
        getRatiosTTM(symbol),
        getDCF(symbol),
        getEnterpriseValue(symbol)
    ]);

    return { ratios, dcf, ev };
});

// ============================================================================
// NEW TYPE DEFINITIONS - Key Metrics, Scores, Analyst Data
// ============================================================================

export interface KeyMetricsTTM {
    revenuePerShareTTM: number;
    netIncomePerShareTTM: number;
    operatingCashFlowPerShareTTM: number;
    freeCashFlowPerShareTTM: number;
    cashPerShareTTM: number;
    bookValuePerShareTTM: number;
    tangibleBookValuePerShareTTM: number;
    shareholdersEquityPerShareTTM: number;
    interestDebtPerShareTTM: number;
    marketCapTTM: number;
    enterpriseValueTTM: number;
    peRatioTTM: number;
    priceToSalesRatioTTM: number;
    pocfratioTTM: number;
    pfcfRatioTTM: number;
    pbRatioTTM: number;
    ptbRatioTTM: number;
    evToSalesTTM: number;
    enterpriseValueOverEBITDATTM: number;
    evToOperatingCashFlowTTM: number;
    evToFreeCashFlowTTM: number;
    earningsYieldTTM: number;
    freeCashFlowYieldTTM: number;
    debtToEquityTTM: number;
    debtToAssetsTTM: number;
    netDebtToEBITDATTM: number;
    currentRatioTTM: number;
    interestCoverageTTM: number;
    incomeQualityTTM: number;
    dividendYieldTTM: number;
    payoutRatioTTM: number;
    salesGeneralAndAdministrativeToRevenueTTM: number;
    researchAndDevelopementToRevenueTTM: number;
    intangiblesToTotalAssetsTTM: number;
    capexToOperatingCashFlowTTM: number;
    capexToRevenueTTM: number;
    capexToDepreciationTTM: number;
    stockBasedCompensationToRevenueTTM: number;
    grahamNumberTTM: number;
    roicTTM: number;
    returnOnTangibleAssetsTTM: number;
    grahamNetNetTTM: number;
    workingCapitalTTM: number;
    tangibleAssetValueTTM: number;
    netCurrentAssetValueTTM: number;
    investedCapitalTTM: number;
    averageReceivablesTTM: number;
    averagePayablesTTM: number;
    averageInventoryTTM: number;
    daysSalesOutstandingTTM: number;
    daysPayablesOutstandingTTM: number;
    daysOfInventoryOnHandTTM: number;
    receivablesTurnoverTTM: number;
    payablesTurnoverTTM: number;
    inventoryTurnoverTTM: number;
    roeTTM: number;
    capexPerShareTTM: number;
}



export interface OwnerEarnings {
    symbol: string;
    date: string;
    averagePPE: number;
    maintenanceCapex: number;
    ownersEarnings: number;
    growthCapex: number;
    ownersEarningsPerShare: number;
}

export interface PriceTargetConsensus {
    symbol: string;
    targetHigh: number;
    targetLow: number;
    targetConsensus: number;
    targetMedian: number;
}

export interface GradesConsensus {
    symbol: string;
    strongBuy: number;
    buy: number;
    hold: number;
    sell: number;
    strongSell: number;
    consensus: string;
}



// ============================================================================
// NEW SERVER ACTIONS
// ============================================================================

/**
 * Fetch Key Metrics TTM (ROE, ROIC, EV/EBITDA, Graham Number, etc.)
 * Uses Yahoo Finance as primary source (works on Vercel)
 */
export const getKeyMetricsTTM = cache(async (symbol: string): Promise<{ symbol: string; keyMetrics: KeyMetricsTTM[] } | null> => {
    // Try Yahoo Finance first (works on Vercel)
    const yahooData = await getYahooFinancialData(symbol);
    if (yahooData.keyMetrics) {
        return { symbol, keyMetrics: [yahooData.keyMetrics] };
    }
    
    // Fallback to Python backend (only works locally)
    if (!IS_SERVERLESS) {
        const data = await fetchFromBackend<{ symbol: string; keyMetrics: KeyMetricsTTM[] }>(`/key-metrics-ttm/${symbol}`);
        return data;
    }
    
    return null;
});

/**
 * Fetch Financial Scores (Altman Z-Score + Piotroski Score)
 */


/**
 * Fetch Owner Earnings (Buffett's preferred metric)
 */
export const getOwnerEarnings = cache(async (symbol: string): Promise<{ symbol: string; ownerEarnings: OwnerEarnings[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; ownerEarnings: OwnerEarnings[] }>(`/owner-earnings/${symbol}`);
    return data;
});

/**
 * Fetch Analyst Price Target Consensus
 */
export const getPriceTarget = cache(async (symbol: string): Promise<{ symbol: string; priceTarget: PriceTargetConsensus[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; priceTarget: PriceTargetConsensus[] }>(`/price-target/${symbol}`);
    return data;
});

/**
 * Fetch Stock Grades Consensus (Buy/Hold/Sell)
 */
export const getGrades = cache(async (symbol: string): Promise<{ symbol: string; grades: GradesConsensus[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; grades: GradesConsensus[] }>(`/grades/${symbol}`);
    return data;
});

/**
 * Fetch Stock Peers for comparison
 */


/**
 * Get comprehensive analysis data in one call (optimized for StockAnalysis component)
 */
export const getComprehensiveAnalysis = cache(async (symbol: string) => {
    const [keyMetrics, scores, ownerEarnings, priceTarget, grades, peers] = await Promise.all([
        getKeyMetricsTTM(symbol),
        getFinancialScores(symbol),
        getOwnerEarnings(symbol),
        getPriceTarget(symbol),
        getGrades(symbol),
        getStockPeers(symbol)
    ]);

    return { keyMetrics, scores, ownerEarnings, priceTarget, grades, peers };
});

// ============================================================================
// PRIORITY APIs - AI/RAG, Trading Signals, WACC
// ============================================================================

export interface EarningsTranscript {
    symbol: string;
    quarter: number;
    year: number;
    date: string;
    content: string;
}

export interface InsiderTrade {
    symbol: string;
    filingDate: string;
    transactionDate: string;
    reportingName: string;
    reportingTitle?: string;
    typeOfTransaction: string;
    securitiesOwned: number;
    securitiesTransacted: number;
    price: number;
    link: string;
}

export interface TreasuryRate {
    date: string;
    month1: number;
    month2: number;
    month3: number;
    month6: number;
    year1: number;
    year2: number;
    year3: number;
    year5: number;
    year7: number;
    year10: number;
    year20: number;
    year30: number;
}

export interface AnalystEstimate {
    symbol: string;
    date: string;
    revenueAvg: number;
    revenueHigh: number;
    revenueLow: number;
    epsAvg: number;
    epsHigh: number;
    epsLow: number;
    numAnalystsRevenue: number;
    numAnalystsEps: number;
}

export interface PressRelease {
    symbol: string;
    publishedDate: string;
    title: string;
    text: string;
    image?: string;
    url?: string;
    site?: string;
}

/**
 * Fetch Earnings Transcript for AI/RAG analysis
 */
export const getEarningsTranscript = cache(async (
    symbol: string,
    year?: number,
    quarter?: number
): Promise<{ symbol: string; transcripts: EarningsTranscript[] } | null> => {
    let endpoint = `/earnings-transcript/${symbol}`;
    const params = new URLSearchParams();
    if (year) params.append('year', year.toString());
    if (quarter) params.append('quarter', quarter.toString());
    if (params.toString()) endpoint += `?${params.toString()}`;

    const data = await fetchFromBackend<{ symbol: string; transcripts: EarningsTranscript[] }>(endpoint);
    return data;
});

/**
 * Fetch Insider Trading data (CEO/CFO buy/sell signals)
 */
export const getInsiderTrading = cache(async (
    symbol: string,
    limit: number = 50
): Promise<{ symbol: string; insiderTrades: InsiderTrade[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; insiderTrades: InsiderTrade[] }>(
        `/insider-trading/${symbol}?limit=${limit}`
    );
    return data;
});

/**
 * Fetch Treasury Rates (10Y for Risk-Free Rate in WACC)
 */
export const getTreasuryRates = cache(async (): Promise<{ treasuryRates: TreasuryRate[] } | null> => {
    const data = await fetchFromBackend<{ treasuryRates: TreasuryRate[] }>('/treasury-rates');
    return data;
});

/**
 * Fetch Analyst Estimates (Future EPS/Revenue projections)
 */
export const getAnalystEstimates = cache(async (
    symbol: string,
    period: 'annual' | 'quarter' = 'annual',
    limit: number = 5
): Promise<{ symbol: string; estimates: AnalystEstimate[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; estimates: AnalystEstimate[] }>(
        `/analyst-estimates/${symbol}?period=${period}&limit=${limit}`
    );
    return data;
});

/**
 * Fetch Official Press Releases
 */
export const getPressReleases = cache(async (
    symbol: string,
    limit: number = 20
): Promise<{ symbol: string; pressReleases: PressRelease[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; pressReleases: PressRelease[] }>(
        `/press-releases/${symbol}?limit=${limit}`
    );
    return data;
});

/**
 * Get AI/RAG context data in one call
 */
export const getAIContextData = cache(async (symbol: string) => {
    const [transcript, insiderTrades, estimates] = await Promise.all([
        getEarningsTranscript(symbol),
        getInsiderTrading(symbol, 20),
        getAnalystEstimates(symbol, 'annual', 3)
    ]);

    return { transcript, insiderTrades, estimates };
});

// ============================================================================
// MARKET MOVERS & SCREENER ACTIONS
// ============================================================================

/**
 * Fetch Market Movers (Gainers, Losers, Active)
 */
/**
 * Fetch Market Movers (Gainers, Losers, Active)
 */
export const getMarketMovers = cache(async (type: 'gainers' | 'losers' | 'active'): Promise<any[] | null> => {
    const data = await fetchFromBackend<any>(`/market-movers/${type}`);
    // Backend returns { gainers: [...] } or { losers: [...] } etc.
    if (!data) return [];
    if (type === 'gainers') return data.gainers || [];
    if (type === 'losers') return data.losers || [];
    if (type === 'active') return data.actives || [];
    return [];
});

export interface ScreenerFilters {
    marketCapMoreThan?: number;
    sector?: string;
    limit?: number;
}

/**
 * Fetch Stocks via Screener
 */
export const getScreenerStocks = cache(async (filters: ScreenerFilters): Promise<any[] | null> => {
    const { marketCapMoreThan, sector, limit = 20 } = filters;
    const params = new URLSearchParams();
    if (marketCapMoreThan) params.append('marketCapMoreThan', marketCapMoreThan.toString());
    if (sector) params.append('sector', sector || '');
    params.append('limit', limit.toString());

    const data = await fetchFromBackend<{ screener: any[] }>(`/screener?${params.toString()}`);
    return data?.screener || [];
});

// ============================================================================
// EARNINGS & NEWS ACTIONS
// ============================================================================

export interface FmpArticle {
    title: string;
    date: string;
    content: string;
    tickers: string;
    image: string;
    link: string;
    author: string;
    site: string;
}

export interface GeneralNewsArticle {
    symbol: string | null;
    publishedDate: string;
    publisher: string;
    title: string;
    image: string;
    site: string;
    text: string;
    url: string;
}

export interface EarningsTranscript {
    symbol: string;
    quarter: number;
    year: number;
    date: string;
    content: string;
}

/**
 * Fetch Earnings Transcripts List
 */
export const getEarningsTranscriptsList = cache(async (symbol: string): Promise<any[]> => {
    const data = await fetchFromBackend<{ transcripts: any[] }>(`/earnings-transcript-list/${symbol}`);
    return data?.transcripts || [];
});

/**
 * Fetch specific Earnings Transcript
 */
export const getEarningsTranscriptContent = cache(async (symbol: string, year: number, quarter: number): Promise<EarningsTranscript | null> => {
    const data = await fetchFromBackend<{ transcript: EarningsTranscript[] }>(`/earnings-transcript/${symbol}?year=${year}&quarter=${quarter}`);
    // API returns array of 1
    return data?.transcript?.[0] || null;
});

/**
 * Fetch FMP Articles
 */
export const getFmpArticles = cache(async (page: number = 0, limit: number = 20): Promise<FmpArticle[]> => {
    const data = await fetchFromBackend<FmpArticle[]>(`/news/fmp-articles?page=${page}&limit=${limit}`);
    return data || [];
});

/**
 * Fetch General News
 */
export const getGeneralNews = cache(async (page: number = 0, limit: number = 20): Promise<GeneralNewsArticle[]> => {
    const data = await fetchFromBackend<GeneralNewsArticle[]>(`/news/general?page=${page}&limit=${limit}`);
    return data || [];
});
export interface MarketNewsArticle {
    category: string;
    datetime: number;
    headline: string;
    id: number | string;
    image: string;
    related: string;
    source: string;
    summary: string;
    url: string;
}

export const getCompanyNews = cache(async (symbol: string, limit: number = 20): Promise<MarketNewsArticle[]> => {
    try {
        const data = await fetchFromBackend<MarketNewsArticle[]>(`/company-news/${symbol}?limit=${limit}`);
        return data || [];
    } catch (error) {
        console.error("Error fetching company news:", error);
        return [];
    }
});

export interface Dividend {
    date: string;
    label: string;
    adjDividend: number;
    dividend: number;
    recordDate: string;
    paymentDate: string;
    declarationDate: string;
}

/**
 * Fetch dividends from Yahoo Finance (works on Vercel)
 */
async function getDividendsFromYahoo(symbol: string): Promise<Dividend[]> {
    try {
        // Yahoo Finance v8 API for dividends
        const now = Math.floor(Date.now() / 1000);
        const fiveYearsAgo = now - (5 * 365 * 24 * 60 * 60);
        
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?period1=${fiveYearsAgo}&period2=${now}&interval=1mo&events=div`;
        
        const response = await fetch(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            },
            next: { revalidate: 86400 }, // Cache 24 hours
        });
        
        if (!response.ok) {
            console.warn(`Yahoo Finance dividends failed for ${symbol}: ${response.status}`);
            return [];
        }
        
        const data = await response.json();
        const events = data?.chart?.result?.[0]?.events?.dividends;
        
        if (!events || typeof events !== 'object') {
            return [];
        }
        
        // Convert Yahoo format to our Dividend interface
        const dividends: Dividend[] = Object.values(events).map((div: any) => {
            const date = new Date(div.date * 1000);
            return {
                date: date.toISOString().split('T')[0],
                label: `${date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}`,
                adjDividend: div.amount || 0,
                dividend: div.amount || 0,
                recordDate: date.toISOString().split('T')[0],
                paymentDate: date.toISOString().split('T')[0],
                declarationDate: date.toISOString().split('T')[0],
            };
        });
        
        // Sort by date descending (most recent first)
        return dividends.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
        
    } catch (error) {
        console.error("Error fetching dividends from Yahoo:", error);
        return [];
    }
}

export const getDividends = cache(async (symbol: string): Promise<Dividend[]> => {
    // Primero intentar Yahoo Finance (funciona en Vercel)
    const yahooDividends = await getDividendsFromYahoo(symbol);
    if (yahooDividends.length > 0) {
        return yahooDividends;
    }
    
    // Fallback al backend Python (solo funciona localmente)
    if (!IS_SERVERLESS) {
        try {
            const data = await fetchFromBackend<Dividend[] | { error: string }>(`/dividends/${symbol}`);
            if (data && Array.isArray(data)) {
                return data;
            }
        } catch (error) {
            console.error("Error fetching dividends from backend:", error);
        }
    }
    
    return [];
});

export interface FinancialScore {
    symbol: string;
    altmanZScore: number;
    piotroskiScore: number;
    workingCapital: number;
    totalAssets: number;
    retainedEarnings: number;
    ebit: number;
    marketCap: number;
    totalLiabilities: number;
    revenue: number;
}

export const getFinancialScores = cache(async (symbol: string): Promise<FinancialScore | null> => {
    try {
        const data = await fetchFromBackend<FinancialScore[]>(`/financial-scores/${symbol}`);
        return data && data.length > 0 ? data[0] : null;
    } catch (error) {
        console.error("Error fetching financial scores:", error);
        return null;
    }
});

export interface PeerCompany {
    symbol: string;
    companyName: string;
    price: number;
    mktCap: number;
}

/**
 * Get stock peers from Yahoo Finance
 */
async function getYahooPeers(symbol: string): Promise<PeerCompany[]> {
    try {
        const url = `https://query1.finance.yahoo.com/v10/finance/quoteSummary/${encodeURIComponent(symbol)}?modules=recommendationTrend,summaryProfile`;
        
        const response = await fetch(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            },
            next: { revalidate: 86400 }, // Cache 24 hours
        });
        
        if (!response.ok) return [];
        
        const data = await response.json();
        const profile = data?.quoteSummary?.result?.[0]?.summaryProfile;
        
        // Yahoo doesn't provide direct peers, but we can use sector/industry to suggest similar stocks
        // For now, return empty and rely on Finnhub peers
        return [];
        
    } catch (error) {
        return [];
    }
}

/**
 * Get stock peers from Finnhub
 */
async function getFinnhubPeers(symbol: string): Promise<string[]> {
    try {
        const token = process.env.FINNHUB_API_KEY;
        if (!token) return [];
        
        const url = `https://finnhub.io/api/v1/stock/peers?symbol=${encodeURIComponent(symbol)}&token=${token}`;
        
        const response = await fetch(url, {
            next: { revalidate: 86400 }, // Cache 24 hours
        });
        
        if (!response.ok) return [];
        
        const data = await response.json();
        return Array.isArray(data) ? data.filter((s: string) => s !== symbol) : [];
        
    } catch (error) {
        return [];
    }
}

export const getStockPeers = cache(async (symbol: string): Promise<PeerCompany[]> => {
    // Try Finnhub first (they have good peer data)
    const finnhubPeers = await getFinnhubPeers(symbol);
    if (finnhubPeers.length > 0) {
        // Convert to PeerCompany format (basic info only)
        return finnhubPeers.slice(0, 8).map(peerSymbol => ({
            symbol: peerSymbol,
            companyName: peerSymbol, // Will be resolved by UI if needed
            price: 0,
            mktCap: 0,
        }));
    }
    
    // Fallback to Python backend (only works locally)
    if (!IS_SERVERLESS) {
        try {
            const data = await fetchFromBackend<PeerCompany[]>(`/stock-peers/${symbol}`);
            return data || [];
        } catch (error) {
            console.error("Error fetching peers:", error);
        }
    }
    
    return [];
});

/**
 * Fetch GARP Strategy Picks
 */
export interface GarpStock {
    symbol: string;
    companyName: string;
    price: number;
    doe: number; // ROE
    peg: number;
    sma200: number;
    sector: string;
    industry: string;
}

export const getGarpStrategy = cache(async (limit: number = 20): Promise<{ strategy: string; count: number; data: GarpStock[] } | null> => {
    // En Vercel/serverless, no hay backend Python disponible
    if (IS_SERVERLESS) {
        return null;
    }
    
    // Force no-store to ensure we get fresh data from the python backend every time
    // This is crucial for strategies that might change daily/hourly
    try {
        const response = await fetch(`${FMP_BACKEND_URL}/strategies/garp?limit=${limit}`, {
            cache: 'no-store',
            next: { revalidate: 0 }
        });

        if (!response.ok) return null;
        return await response.json();
    } catch (error) {
        console.error("Error fetching GARP strategy:", error);
        return null;
    }
});

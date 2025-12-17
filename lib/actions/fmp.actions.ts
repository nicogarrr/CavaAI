'use server';

import { cache } from 'react';

const FMP_BACKEND_URL = process.env.FMP_BACKEND_URL || 'http://localhost:8000';

/**
 * Generic fetch helper for FMP backend
 */
async function fetchFromBackend<T>(endpoint: string): Promise<T | null> {
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
 * Fetch TTM ratios (PER, ROIC, ROE, P/S, P/B)
 */
export const getRatiosTTM = cache(async (symbol: string): Promise<{ symbol: string; ratios: RatiosTTM[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; ratios: RatiosTTM[] }>(`/ratios-ttm/${symbol}`);
    return data;
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

export interface FinancialScores {
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

export interface StockPeers {
    symbol: string;
    peersList: string[];
}

// ============================================================================
// NEW SERVER ACTIONS
// ============================================================================

/**
 * Fetch Key Metrics TTM (ROE, ROIC, EV/EBITDA, Graham Number, etc.)
 */
export const getKeyMetricsTTM = cache(async (symbol: string): Promise<{ symbol: string; keyMetrics: KeyMetricsTTM[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; keyMetrics: KeyMetricsTTM[] }>(`/key-metrics-ttm/${symbol}`);
    return data;
});

/**
 * Fetch Financial Scores (Altman Z-Score + Piotroski Score)
 */
export const getFinancialScores = cache(async (symbol: string): Promise<{ symbol: string; scores: FinancialScores[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; scores: FinancialScores[] }>(`/financial-scores/${symbol}`);
    return data;
});

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
export const getStockPeers = cache(async (symbol: string): Promise<{ symbol: string; peers: StockPeers[] } | null> => {
    const data = await fetchFromBackend<{ symbol: string; peers: StockPeers[] }>(`/peers/${symbol}`);
    return data;
});

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
    estimatedRevenueAvg: number;
    estimatedRevenueHigh: number;
    estimatedRevenueLow: number;
    estimatedEpsAvg: number;
    estimatedEpsHigh: number;
    estimatedEpsLow: number;
    numberAnalystEstimatedRevenue: number;
    numberAnalystsEstimatedEps: number;
}

export interface PressRelease {
    symbol: string;
    date: string;
    title: string;
    text: string;
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

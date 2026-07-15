'use server';

import { getCandles, getStockFinancialDataLight } from './finnhub.actions';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { calculateAdvancedStockScore } from '@/lib/utils/advancedStockScoring';
import {
  PROPICKS_STRATEGIES,
  calculateStrategyScore,
  getStrategyById,
} from '@/lib/utils/proPicksStrategies';

export interface ProPick {
  symbol: string;
  company: string;
  score: number;
  grade: string;
  strategyScore?: number;
  strategy?: string;
  categoryScores: {
    value: number;
    growth: number;
    profitability: number;
    cashFlow: number;
    momentum: number;
    debtLiquidity: number;
  };
  reasons: string[];
  currentPrice: number;
  sector?: string;
  exchange?: string;
  vsSector?: {
    value: number;
    growth: number;
    profitability: number;
    cashFlow: number;
    momentum: number;
    debtLiquidity: number;
  };
  upsidePotential?: number;
  isStrongBuy?: boolean;
  targetPrice?: number;
}

const LIQUID_UNIVERSE = [
  'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'AVGO', 'ORCL', 'CRM', 'AMD',
  'JPM', 'BAC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BLK', 'SCHW', 'C',
  'LLY', 'UNH', 'JNJ', 'MRK', 'ABBV', 'TMO', 'ABT', 'ISRG', 'GILD', 'AMGN',
  'WMT', 'COST', 'HD', 'MCD', 'BKNG', 'TJX', 'LOW', 'SBUX', 'NKE', 'DIS',
  'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'CAT', 'GE', 'RTX', 'HON', 'ETN',
  'NEE', 'DUK', 'SO', 'CEG', 'VST', 'LIN', 'FCX', 'NEM', 'SHW', 'APD',
  'PLD', 'AMT', 'EQIX', 'WELL', 'VICI', 'TSM', 'ASML', 'NVO', 'MELI', 'SE',
] as const;

type FinancialData = Awaited<ReturnType<typeof getStockFinancialDataLight>>;

async function evaluateSymbol(symbol: string, strategyId: string): Promise<ProPick | null> {
  try {
    const financialData: FinancialData = await getStockFinancialDataLight(symbol);
    if (!financialData?.profile) return null;

    const profile = financialData.profile as Record<string, unknown>;
    const quote = financialData.quote as Record<string, unknown> | undefined;
    const currentPrice = Number(quote?.c ?? quote?.price ?? 0);
    const sector = String(profile.finnhubIndustry ?? profile.industry ?? 'Unknown');
    const strategy = getStrategyById(strategyId) ?? PROPICKS_STRATEGIES[0];

    let historicalData: { prices: number[]; dates: number[] } | undefined;
    const to = Math.floor(Date.now() / 1000);
    const candles = await getCandles(symbol, to - 365 * 24 * 60 * 60, to, 'D', 3600).catch(() => null);
    if (candles?.s === 'ok' && candles.c.length > 0) {
      historicalData = { prices: candles.c, dates: candles.t };
    }

    const advanced = await calculateAdvancedStockScore(financialData, historicalData);
    const targetPrice = Number(financialData.priceTarget?.targetMean ?? 0);
    const upsidePotential = currentPrice > 0 && targetPrice > 0
      ? ((targetPrice - currentPrice) / currentPrice) * 100
      : 0;

    return {
      symbol,
      company: String(profile.name ?? symbol),
      score: advanced.overallScore,
      grade: advanced.grade,
      strategyScore: calculateStrategyScore(advanced, strategy),
      strategy: strategy.id,
      categoryScores: advanced.categoryScores,
      reasons: [...advanced.reasons.strengths, ...advanced.reasons.opportunities].slice(0, 5),
      currentPrice,
      sector,
      exchange: profile.exchange ? String(profile.exchange) : undefined,
      vsSector: advanced.sectorComparison?.vsSector,
      targetPrice: targetPrice || undefined,
      upsidePotential: targetPrice ? upsidePotential : undefined,
      isStrongBuy: advanced.overallScore >= 80 && upsidePotential > 15,
    };
  } catch (error) {
    console.error(`No se pudo evaluar ${symbol}`, error);
    return null;
  }
}

async function evaluateUniverse(strategyId: string): Promise<ProPick[]> {
  const picks: ProPick[] = [];
  const batchSize = 8;
  for (let index = 0; index < LIQUID_UNIVERSE.length; index += batchSize) {
    const batch = LIQUID_UNIVERSE.slice(index, index + batchSize);
    const evaluated = await Promise.all(batch.map((symbol) => evaluateSymbol(symbol, strategyId)));
    picks.push(...evaluated.filter((pick): pick is ProPick => pick !== null));
  }
  return picks;
}

export async function generateProPicks(limit = 5, strategyId = 'adaptive'): Promise<ProPick[]> {
  await requireAuthenticatedUser();
  const picks = await evaluateUniverse(strategyId);
  const qualified = picks.filter((pick) => pick.score >= 60);
  return (qualified.length > 0 ? qualified : picks)
    .sort((left, right) => (right.strategyScore ?? right.score) - (left.strategyScore ?? left.score))
    .slice(0, Math.max(1, Math.min(limit, 100)));
}

export async function generateProPicksForStrategy(strategyId: string, limit = 10): Promise<ProPick[]> {
  return generateProPicks(limit, strategyId);
}

export async function getAvailableStrategies() {
  await requireAuthenticatedUser();
  return PROPICKS_STRATEGIES.map(({ id, name, description }) => ({ id, name, description }));
}

export interface EnhancedProPicksFilters {
  timePeriod?: 'week' | 'month' | 'quarter' | 'year';
  limit?: number;
  minScore?: number;
  sector?: string;
  sortBy?: 'score' | 'momentum' | 'value' | 'growth' | 'profitability';
}

const SECTOR_ALIASES: Record<string, string[]> = {
  Technology: ['technology', 'software', 'semiconductor', 'internet'],
  Healthcare: ['health', 'biotech', 'pharma', 'medical'],
  'Financial Services': ['financial', 'bank', 'insurance', 'asset management'],
  'Consumer Discretionary': ['consumer', 'retail', 'apparel', 'hotel', 'restaurant'],
  Industrials: ['industrial', 'aerospace', 'defense', 'machinery'],
  Energy: ['energy', 'oil', 'gas', 'petroleum'],
  Utilities: ['utilities', 'electric', 'power'],
  'Real Estate': ['real estate', 'reit', 'property'],
  Materials: ['materials', 'chemical', 'mining', 'metal'],
};

export async function generateEnhancedProPicks(filters: EnhancedProPicksFilters = {}): Promise<ProPick[]> {
  await requireAuthenticatedUser();
  const { limit = 20, minScore = 70, sector = 'all', sortBy = 'score' } = filters;
  let picks = await evaluateUniverse('adaptive');
  picks = picks.filter((pick) => pick.score >= minScore);

  if (sector !== 'all') {
    const aliases = SECTOR_ALIASES[sector] ?? [sector.toLowerCase()];
    picks = picks.filter((pick) => aliases.some((alias) => pick.sector?.toLowerCase().includes(alias)));
  }

  const scoreFor = (pick: ProPick) => {
    if (sortBy === 'score') return pick.strategyScore ?? pick.score;
    return pick.categoryScores[sortBy];
  };
  return picks.sort((left, right) => scoreFor(right) - scoreFor(left)).slice(0, Math.max(1, Math.min(limit, 100)));
}

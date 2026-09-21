'use server';

import { getCandles, getStockFinancialDataLight } from './finnhub.actions';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { calculateAdvancedStockScore, type AdvancedScoreData } from '@/lib/utils/advancedStockScoring';
import {
  PROPICKS_STRATEGIES,
  calculateStrategyScore,
  getStrategyById,
} from '@/lib/utils/proPicksStrategies';

export interface ConfidenceReason {
  /** Texto mostrado en UI. Siempre incluye `value` para que sea verificable. */
  text: string;
  /** Clave de `facts` de la que sale el número. Nunca referencia métricas inexistentes. */
  metric: string;
  value: number | string;
}

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
  /**
   * Confianza explicada: 2-3 motivos trazables a `facts` (métricas reales).
   * Regla: ningún motivo inventa números; cada `value` existe en `facts`
   * y aparece en `text` (validado por lib/utils/propicksValidation.ts).
   */
  confidenceReasons: ConfidenceReason[];
  /** 0-100. Fórmula: base por banda de score + bonus reales (ver buildConfidence). */
  confidence: number;
  /** Alta (>=80) · Media (>=65) · Baja (<65). */
  confidenceLevel: 'Alta' | 'Media' | 'Baja';
  /** Corte temporal ISO: ningún dato posterior a asOf entra al cálculo. */
  asOf: string;
  /** Foto de métricas reales tras el pick (precio, objetivo, categorías...). */
  facts: Record<string, number | string>;
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

const CATEGORY_LABELS: Record<keyof AdvancedScoreData['categoryScores'], string> = {
  value: 'Valor',
  growth: 'Crecimiento',
  profitability: 'Rentabilidad',
  cashFlow: 'Flujo de caja',
  momentum: 'Momentum',
  debtLiquidity: 'Salud financiera',
};

const round1 = (n: number) => Math.round(n * 10) / 10;

/**
 * Confianza explicada del pick (0-100).
 * Fórmula calibrada y sin magia:
 *   base por banda de score: >=80 → 82 · 70-79 → 72 · 60-69 → 60 · <60 → 45
 *   +6 si upside real > 15% (precio objetivo de analista vs precio actual)
 *   +4 si ≥2 categorías superan a su sector en >5 puntos
 *   +4 si la mejor categoría ≥ 80
 *   techo 97. Nivel: Alta (>=80) · Media (>=65) · Baja (<65).
 * Los motivos se eligen solo entre métricas presentes en `facts`.
 */
function buildConfidence(
  score: number,
  advanced: AdvancedScoreData,
  upsidePotential: number,
  targetPrice: number,
  currentPrice: number
): { confidence: number; confidenceLevel: ProPick['confidenceLevel']; confidenceReasons: ConfidenceReason[]; facts: Record<string, number | string> } {
  const facts: Record<string, number | string> = { ...advanced.facts };
  if (targetPrice > 0) facts['targetMean'] = round1(targetPrice);
  if (upsidePotential !== 0) facts['upside'] = round1(upsidePotential);
  (Object.keys(advanced.categoryScores) as Array<keyof AdvancedScoreData['categoryScores']>).forEach((key) => {
    facts[`cat_${key}`] = advanced.categoryScores[key];
  });

  let confidence = score >= 80 ? 82 : score >= 70 ? 72 : score >= 60 ? 60 : 45;
  if (upsidePotential > 15) confidence += 6;
  const strongVsSector = Object.values(advanced.sectorComparison?.vsSector ?? {}).filter((d) => d > 5).length;
  if (strongVsSector >= 2) confidence += 4;
  const bestCategory = (Object.entries(advanced.categoryScores) as Array<[keyof AdvancedScoreData['categoryScores'], number]>)
    .sort((a, b) => b[1] - a[1])[0];
  if (bestCategory && bestCategory[1] >= 80) confidence += 4;
  confidence = Math.max(5, Math.min(97, Math.round(confidence)));
  const confidenceLevel: ProPick['confidenceLevel'] = confidence >= 80 ? 'Alta' : confidence >= 65 ? 'Media' : 'Baja';

  // Motivos: solo métricas reales presentes en facts, valor incluido en el texto.
  const candidates: ConfidenceReason[] = [];
  if (targetPrice > 0 && upsidePotential > 5) {
    const v = round1(upsidePotential);
    candidates.push({
      metric: 'upside',
      value: v,
      text: `Potencial alcista del ${v}% (objetivo $${round1(targetPrice)} vs $${round1(currentPrice)})`,
    });
  }
  const deltas = advanced.sectorComparison?.vsSector;
  if (deltas && bestCategory && deltas[bestCategory[0]] > 5) {
    const [key, catScore] = bestCategory;
    const delta = Math.round(deltas[key]);
    candidates.push({
      metric: `cat_${key}`,
      value: catScore,
      text: `${CATEGORY_LABELS[key]} ${catScore}/100 (+${delta} vs sector)`,
    });
  }
  const f = facts;
  if (typeof f['return12M'] === 'number' && f['return12M'] > 10) {
    candidates.push({ metric: 'return12M', value: f['return12M'], text: `Sube un ${f['return12M']}% en 12 meses` });
  }
  if (typeof f['vsSP500'] === 'number' && f['vsSP500'] > 5) {
    candidates.push({ metric: 'vsSP500', value: f['vsSP500'], text: `Supera al S&P 500 en ${f['vsSP500']} puntos` });
  }
  if (typeof f['proximity52W'] === 'number' && f['proximity52W'] > 95) {
    candidates.push({ metric: 'proximity52W', value: f['proximity52W'], text: `Cotiza al ${f['proximity52W']}% de su máximo de 52 semanas` });
  }
  if (typeof f['currentRatio'] === 'number' && f['currentRatio'] > 2) {
    candidates.push({ metric: 'currentRatio', value: f['currentRatio'], text: `Liquidez sólida (ratio ${f['currentRatio']})` });
  }
  // Respaldo trazable: mejores categorías aunque no batan al sector
  // (los números siguen siendo reales). Garantiza ≥2 motivos.
  if (candidates.length < 2) {
    const used = new Set(candidates.map((c) => c.metric));
    const ranked = (Object.entries(advanced.categoryScores) as Array<[keyof AdvancedScoreData['categoryScores'], number]>)
      .sort((a, b) => b[1] - a[1]);
    for (const [key, catScore] of ranked) {
      if (candidates.length >= 2) break;
      if (used.has(`cat_${key}`)) continue;
      candidates.push({
        metric: `cat_${key}`,
        value: catScore,
        text: `Su punto fuerte es ${CATEGORY_LABELS[key]} (${catScore}/100)`,
      });
    }
  }

  return { confidence, confidenceLevel, confidenceReasons: candidates.slice(0, 3), facts };
}

async function evaluateSymbol(symbol: string, strategyId: string): Promise<ProPick | null> {
  try {
    // financialData y candles son independientes: en paralelo en vez de en
    // serie (ahorra ~1 RTT Finnhub por símbolo × 70 del universo).
    const to = Math.floor(Date.now() / 1000);
    const [financialData, candles] = await Promise.all([
      getStockFinancialDataLight(symbol),
      getCandles(symbol, to - 365 * 24 * 60 * 60, to, 'D', 3600).catch(() => null),
    ]);
    const typedFinancialData: FinancialData = financialData;
    if (!typedFinancialData?.profile) return null;

    const profile = typedFinancialData.profile as Record<string, unknown>;
    const quote = typedFinancialData.quote as Record<string, unknown> | undefined;
    const currentPrice = Number(quote?.c ?? quote?.price ?? 0);
    const sector = String(profile.finnhubIndustry ?? profile.industry ?? 'Unknown');
    const strategy = getStrategyById(strategyId) ?? PROPICKS_STRATEGIES[0];

    let historicalData: { prices: number[]; dates: number[] } | undefined;
    if (candles?.s === 'ok' && candles.c.length > 0) {
      historicalData = { prices: candles.c, dates: candles.t };
    }

    const advanced = await calculateAdvancedStockScore(typedFinancialData, historicalData);
    const targetPrice = Number(typedFinancialData.priceTarget?.targetMean ?? 0);
    const upsidePotential = currentPrice > 0 && targetPrice > 0
      ? ((targetPrice - currentPrice) / currentPrice) * 100
      : 0;

    const strategyScore = calculateStrategyScore(advanced, strategy);
    const explained = buildConfidence(advanced.overallScore, advanced, upsidePotential, targetPrice, currentPrice);

    return {
      symbol,
      company: String(profile.name ?? symbol),
      score: advanced.overallScore,
      grade: advanced.grade,
      strategyScore,
      strategy: strategy.id,
      categoryScores: advanced.categoryScores,
      reasons: [...advanced.reasons.strengths, ...advanced.reasons.opportunities].slice(0, 5),
      confidenceReasons: explained.confidenceReasons,
      confidence: explained.confidence,
      confidenceLevel: explained.confidenceLevel,
      asOf: advanced.asOf,
      facts: explained.facts,
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

'use server';

import { CACHE_TTL } from '@/lib/constants';

export type FundCategory =
  | 'bitcoin_etf'
  | 'msci_world'
  | 'sp500'
  | 'emerging_markets'
  | 'euro_stoxx_50'
  | 'global_aggregate_bond'
  | 'gold_etf';

export type FundBasics = {
  isin?: string;
  symbol?: string;
  name: string;
  provider?: string;
  domicile?: string;
  currency?: string;
  aumMillions?: number;
  expenseRatio?: number; // TER %
  replication?: 'physical' | 'synthetic' | 'optimized' | string;
  distributing?: boolean;
  inceptionDate?: string;
  url?: string;
};

export type FundPerformance = {
  y1?: number; // 1Y %
  y3?: number; // 3Y % CAGR
  y5?: number; // 5Y % CAGR
  ytd?: number; // YTD %
  trackingDifference?: number; // % vs índice
  volatilityY1?: number; // stdev 1Y
};

export type FundRecord = FundBasics & FundPerformance & {
  category: FundCategory;
  score?: number;
  dataSource?: string;
};

// Adaptadores de fuentes (configurables por .env; si no están, usar fallback público cuando sea posible)
async function fetchFromJustETF(category: FundCategory): Promise<FundRecord[]> {
  // Nota: JustETF no tiene API pública estable; este adaptador espera una función de backend propia o dataset cacheado.
  // Aquí dejamos un placeholder seguro que retorna vacío si no está configurado.
  const base = process.env.JUSTETF_BASE_URL;
  if (!base) return [];
  const res = await fetch(`${base}/api/funds?category=${category}`, { next: { revalidate: CACHE_TTL.SEMI_STATIC_DATA } });
  if (!res.ok) return [];
  return await res.json();
}

async function fetchFromMorningstar(category: FundCategory): Promise<FundRecord[]> {
  const base = process.env.MORNINGSTAR_BASE_URL;
  const key = process.env.MORNINGSTAR_API_KEY;
  if (!base || !key) return [];
  const res = await fetch(`${base}/v1/funds/rank?category=${category}&key=${key}`, { next: { revalidate: CACHE_TTL.SEMI_STATIC_DATA } });
  if (!res.ok) return [];
  return await res.json();
}

async function fetchFromFinect(category: FundCategory): Promise<FundRecord[]> {
  const base = process.env.FINECT_BASE_URL;
  const key = process.env.FINECT_API_KEY;
  if (!base || !key) return [];
  const res = await fetch(`${base}/funds?category=${category}&key=${key}`, { next: { revalidate: CACHE_TTL.SEMI_STATIC_DATA } });
  if (!res.ok) return [];
  return await res.json();
}

// Fallback simple por categoría (lista base de ETFs conocidos)
function fallbackSeeds(category: FundCategory): FundRecord[] {
  const map: Record<FundCategory, FundRecord[]> = {
    bitcoin_etf: [
      { name: 'iShares Bitcoin Trust', symbol: 'IBIT', provider: 'iShares', expenseRatio: 0.25, category: 'bitcoin_etf', dataSource: 'seed' },
      { name: 'Fidelity Wise Origin Bitcoin Fund', symbol: 'FBTC', provider: 'Fidelity', expenseRatio: 0.25, category: 'bitcoin_etf', dataSource: 'seed' },
      { name: 'Vanguard Bitcoin ETF', symbol: 'HODL', provider: 'Vanguard', expenseRatio: 0.25, category: 'bitcoin_etf', dataSource: 'seed' },
    ],
    msci_world: [
      { name: 'iShares Core MSCI World UCITS ETF', symbol: 'IWDA', provider: 'iShares', expenseRatio: 0.20, category: 'msci_world', dataSource: 'seed' },
      { name: 'Vanguard FTSE Developed World UCITS ETF', symbol: 'VEVE', provider: 'Vanguard', expenseRatio: 0.12, category: 'msci_world', dataSource: 'seed' },
      { name: 'Xtrackers MSCI World UCITS ETF', symbol: 'XDWD', provider: 'Xtrackers', expenseRatio: 0.19, category: 'msci_world', dataSource: 'seed' },
    ],
    sp500: [
      { name: 'Vanguard S&P 500 UCITS ETF', symbol: 'VUSA', provider: 'Vanguard', expenseRatio: 0.07, category: 'sp500', dataSource: 'seed' },
      { name: 'iShares Core S&P 500 UCITS ETF', symbol: 'CSPX', provider: 'iShares', expenseRatio: 0.07, category: 'sp500', dataSource: 'seed' },
    ],
    emerging_markets: [
      { name: 'iShares Core MSCI EM IMI UCITS ETF', symbol: 'EIMI', provider: 'iShares', expenseRatio: 0.18, category: 'emerging_markets', dataSource: 'seed' },
      { name: 'Vanguard FTSE EM UCITS ETF', symbol: 'VFEM', provider: 'Vanguard', expenseRatio: 0.22, category: 'emerging_markets', dataSource: 'seed' },
    ],
    euro_stoxx_50: [
      { name: 'iShares EURO STOXX 50 UCITS ETF', symbol: 'EUN2', provider: 'iShares', expenseRatio: 0.10, category: 'euro_stoxx_50', dataSource: 'seed' },
    ],
    global_aggregate_bond: [
      { name: 'iShares Core Global Aggregate Bond UCITS ETF', symbol: 'AGGH', provider: 'iShares', expenseRatio: 0.10, category: 'global_aggregate_bond', dataSource: 'seed' },
    ],
    gold_etf: [
      { name: 'iShares Physical Gold ETC', symbol: 'SGLN', provider: 'iShares', expenseRatio: 0.15, category: 'gold_etf', dataSource: 'seed' },
    ],
  };
  return map[category] || [];
}

// Normalización superficial para homogeneizar campos entre fuentes
function normalize(records: FundRecord[]): FundRecord[] {
  return records.map((r) => ({
    ...r,
    name: r.name?.trim(),
    provider: r.provider?.trim(),
    expenseRatio: r.expenseRatio != null ? Number(r.expenseRatio) : undefined,
    aumMillions: r.aumMillions != null ? Number(r.aumMillions) : undefined,
  }));
}

// Scoring configurable (ponderaciones heurísticas): menor TER, mayor rentabilidad, menor tracking-diff, AUM suficiente
function scoreFund(f: FundRecord): number {
  const ter = f.expenseRatio ?? 0.5; // cuanto menor mejor
  const y1 = f.y1 ?? 0;
  const y3 = f.y3 ?? 0;
  const y5 = f.y5 ?? 0;
  const td = f.trackingDifference ?? 0; // cuanto menor mejor (ideal<=0)
  const vol = f.volatilityY1 ?? 0; // cuanto menor mejor
  const aum = f.aumMillions ?? 0; // penalizar fondos demasiado pequeños

  const terScore = Math.max(0, 100 - ter * 100); // TER 0.10% -> 90 pts
  const perfScore = y1 * 0.3 + y3 * 0.35 + y5 * 0.35; // ponderado
  const tdScore = Math.max(0, 100 - Math.max(0, td) * 100); // penalizar tracking positivo
  const volScore = Math.max(0, 100 - vol * 10);
  const aumScore = Math.min(100, Math.log10(Math.max(1, aum)) * 20); // aum 10,000 -> ~80

  // peso total (ajustable por categoría si se desea)
  const total = terScore * 0.25 + perfScore * 0.45 + tdScore * 0.15 + volScore * 0.05 + aumScore * 0.10;
  return Number(total.toFixed(2));
}

function dedupe(records: FundRecord[]): FundRecord[] {
  const seen = new Set<string>();
  const out: FundRecord[] = [];
  for (const r of records) {
    const key = (r.isin || r.symbol || r.name).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(r);
  }
  return out;
}

export async function getRankedFundsByCategory(category: FundCategory, limit = 10): Promise<FundRecord[]> {
  const [a, b, c] = await Promise.all([
    fetchFromJustETF(category).catch(() => []),
    fetchFromMorningstar(category).catch(() => []),
    fetchFromFinect(category).catch(() => []),
  ]);
  const fallback = fallbackSeeds(category);
  const all = normalize([...a, ...b, ...c, ...fallback].map(r => ({ ...r, category })));
  const unique = dedupe(all);
  const scored = unique.map(f => ({ ...f, score: scoreFund(f) }));
  return scored
    .sort((x, y) => (y.score ?? 0) - (x.score ?? 0))
    .slice(0, limit);
}

export async function getFundCategories(): Promise<{ id: FundCategory; label: string }[]> {
  return [
    { id: 'bitcoin_etf', label: 'Bitcoin ETFs' },
    { id: 'msci_world', label: 'MSCI World' },
    { id: 'sp500', label: 'S&P 500' },
    { id: 'emerging_markets', label: 'Emerging Markets' },
    { id: 'euro_stoxx_50', label: 'EURO STOXX 50' },
    { id: 'global_aggregate_bond', label: 'Global Aggregate Bonds' },
    { id: 'gold_etf', label: 'Gold ETC/ETF' },
  ];
}



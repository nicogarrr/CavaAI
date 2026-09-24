'use server';

import { researchRequest } from '@/lib/research/client';
import { cachedFetch } from '@/lib/cache/memoryTTL';

export type MarketIndex = {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
};

export type MarketMover = {
  ticker: string;
  name: string;
  sector: string;
  /** ISO 4217 de la compañía; null si el backend aún no la sirve */
  currency?: string | null;
  price: number;
  /** null = sin cierre anterior registrado (cambio no medible, nunca 0 inventado) */
  change_pct: number | null;
  volume: number;
  date: string | null;
};

export type MarketMovers = {
  as_of: string | null;
  universe: number;
  gainers: MarketMover[];
  losers: MarketMover[];
  most_active: MarketMover[];
};

/** Gainers/losers/más activas desde precios locales. Vacío honesto si no hay datos. */
export async function getMarketMovers(limit = 10): Promise<MarketMovers> {
  const empty: MarketMovers = { as_of: null, universe: 0, gainers: [], losers: [], most_active: [] };
  try {
    const payload = await cachedFetch<MarketMovers>(
      `market:movers:${limit}`,
      () => researchRequest<MarketMovers>(`/api/market/movers?limit=${limit}`),
      45,
    );
    if (!payload || !Array.isArray(payload.gainers)) return empty;
    return payload;
  } catch (error) {
    console.error('getMarketMovers error:', error);
    return empty;
  }
}
/** Índices reales (S&P 500, Nasdaq, Bitcoin, Oro, Plata) desde el backend. */
export async function getMarketIndices(): Promise<MarketIndex[]> {
  try {
    // Caché corta en memoria (45s): el dashboard y el screener llaman a esta
    // acción en cada render; el payload es idéntico dentro de la ventana.
    const payload = await cachedFetch<{ indices: MarketIndex[] }>(
      'market:indices',
      () => researchRequest<{ indices: MarketIndex[] }>('/api/market/indices'),
      45,
    );
    return payload.indices ?? [];
  } catch (error) {
    console.error('getMarketIndices error:', error);
    return [];
  }
}
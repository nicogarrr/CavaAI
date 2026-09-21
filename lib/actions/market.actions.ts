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
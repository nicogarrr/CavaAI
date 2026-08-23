'use server';

import { researchRequest } from '@/lib/research/client';

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
    const payload = await researchRequest<{ indices: MarketIndex[] }>('/api/market/indices');
    return payload.indices ?? [];
  } catch (error) {
    console.error('getMarketIndices error:', error);
    return [];
  }
}
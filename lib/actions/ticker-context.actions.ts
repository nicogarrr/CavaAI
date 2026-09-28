'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchRequest } from '@/lib/research/client';
import { cachedFetch } from '@/lib/cache/memoryTTL';
import { getWatchlist } from '@/lib/actions/watchlist.actions';

export type TickerContext = {
    portfolioTickers: string[];
    watchlistTickers: string[];
};

/**
 * Tickers presentes en la cartera y en la watchlist del usuario, para los
 * badges «En cartera / En watchlist» (quick win UX 5). Degradación honesta:
 * si una lectura falla, su conjunto queda vacío — ningún badge es nunca una
 * afirmación falsa de pertenencia.
 */
export async function getTickerContext(): Promise<TickerContext> {
    const userId = (await requireAuthenticatedUser()).id;
    const [positions, watchlist] = await Promise.all([
        cachedFetch(
            `portfolio:${userId}:positions`,
            () => researchRequest<Array<{ ticker: string }>>('/api/portfolio/positions', { fast: true }),
            15,
        ).catch(() => [] as Array<{ ticker: string }>),
        getWatchlist().catch(() => [] as Array<{ symbol: string }>),
    ]);
    return {
        portfolioTickers: positions.map((position) => position.ticker.toUpperCase()),
        watchlistTickers: watchlist.map((item) => item.symbol.toUpperCase()),
    };
}

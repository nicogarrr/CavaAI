/**
 * Quick win UX 5: badges «En cartera / En watchlist» junto al ticker en
 * eventos de noticias y movers. Lógica pura, testeable en node.
 */
export type TickerBadge = 'portfolio' | 'watchlist';

export function tickerBadgesFor(
    ticker: string,
    portfolioTickers: ReadonlySet<string>,
    watchlistTickers: ReadonlySet<string>,
): TickerBadge[] {
    const normalized = ticker.trim().toUpperCase();
    const badges: TickerBadge[] = [];
    if (portfolioTickers.has(normalized)) badges.push('portfolio');
    if (watchlistTickers.has(normalized)) badges.push('watchlist');
    return badges;
}

export const TICKER_BADGE_LABELS: Record<TickerBadge, string> = {
    portfolio: 'En cartera',
    watchlist: 'En watchlist',
};

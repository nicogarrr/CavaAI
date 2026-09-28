/**
 * Orden del índice /research por relevancia (quick win UX 6):
 * tesis > cartera > watchlist > resto; empate por ticker (es).
 * Lógica pura, testeable en node (sin imports con alias).
 */

/** Bucket de relevancia: 0 tesis, 1 cartera, 2 watchlist, 3 resto. */
export function researchRelevanceKey(
    ticker: string,
    hasThesis: boolean,
    portfolioTickers: ReadonlySet<string>,
    watchlistTickers: ReadonlySet<string>,
): 0 | 1 | 2 | 3 {
    if (hasThesis) return 0;
    const normalized = ticker.trim().toUpperCase();
    if (portfolioTickers.has(normalized)) return 1;
    if (watchlistTickers.has(normalized)) return 2;
    return 3;
}

/**
 * Orden estable por (bucket, ticker). No muta la entrada. Si los snapshots
 * no se pudieron leer, hasThesis debe ser false para todas: la página
 * degrada a cartera > watchlist > resto sin afirmar tesis inexistentes.
 */
export function sortCompaniesByRelevance<T extends { ticker: string }>(
    companies: readonly T[],
    hasThesis: (company: T) => boolean,
    portfolioTickers: ReadonlySet<string>,
    watchlistTickers: ReadonlySet<string>,
): T[] {
    return [...companies].sort((left, right) => {
        const delta = researchRelevanceKey(left.ticker, hasThesis(left), portfolioTickers, watchlistTickers)
            - researchRelevanceKey(right.ticker, hasThesis(right), portfolioTickers, watchlistTickers);
        return delta !== 0 ? delta : left.ticker.localeCompare(right.ticker, 'es');
    });
}

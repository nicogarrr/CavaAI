/** Atajos de /insider: tickers de cartera y watchlist para no empezar con la
 * pantalla vacía. Solo lectura; sin cartera ni watchlist no se inventa nada. */
export type InsiderShortcuts = { portfolio: string[]; watchlist: string[] };

const clean = (value: unknown): string | null => {
    if (typeof value !== 'string') return null;
    const symbol = value.trim().toUpperCase();
    return symbol || null;
};

export function buildInsiderShortcuts(
    holdings: Array<{ symbol?: string | null; quantity?: number | null }> | null | undefined,
    watchlist: Array<{ symbol?: string | null }> | null | undefined,
    limit = 12,
): InsiderShortcuts {
    const portfolio = Array.from(
        new Set(
            (holdings ?? [])
                .filter((holding) => Number(holding.quantity ?? 0) !== 0)
                .map((holding) => clean(holding.symbol))
                .filter((symbol): symbol is string => symbol !== null),
        ),
    ).slice(0, limit);
    const inPortfolio = new Set(portfolio);
    const watch = Array.from(
        new Set(
            (watchlist ?? [])
                .map((item) => clean(item.symbol))
                .filter((symbol): symbol is string => symbol !== null && !inPortfolio.has(symbol)),
        ),
    ).slice(0, limit);
    return { portfolio, watchlist: watch };
}

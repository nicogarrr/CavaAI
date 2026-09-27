/**
 * Decision de pintado de un factor de cartera: ausente no es cero.
 *
 * Un "0" de puntuacion es una medicion; la ausencia de la metrica que la
 * alimenta no lo es. Cuando el tearsheet no existe, no hay posiciones o el
 * backend falla, los factores llegan en null y la tarjeta debe decir
 * "sin datos", no pintar "0,00": un fallo de red no es una cartera con
 * calidad 0.
 */
export type PortfolioScoreDisplay =
    | { readonly kind: 'no-data' }
    | { readonly kind: 'score'; readonly value: number; readonly isPercent: boolean };

export function portfolioScoreDisplay(
    value: number | null,
    isPercent = false,
): PortfolioScoreDisplay {
    if (value == null) {
        return { kind: 'no-data' };
    }
    return { kind: 'score', value, isPercent };
}

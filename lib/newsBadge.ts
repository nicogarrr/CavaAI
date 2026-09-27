/**
 * F149: insignia de vínculo de un titular de «Noticias destacadas».
 * `article.related` es la compañía QUE MENCIONA el titular según el proveedor
 * (Finnhub...), NO una tenencia del usuario. Solo se afirma vínculo con la
 * cartera cuando el ticker está entre los símbolos reales del usuario.
 */
export type NewsBadge =
    | { kind: 'holding'; ticker: string }
    | { kind: 'mentioned'; ticker: string }
    | { kind: 'general' };

export function newsBadge(
    article: { related?: string | null },
    userSymbols?: string[],
): NewsBadge {
    const related = article.related?.trim().toUpperCase();
    if (!related) return { kind: 'general' };
    const owned = (userSymbols ?? [])
        .map((symbol) => symbol.trim().toUpperCase())
        .includes(related);
    return owned ? { kind: 'holding', ticker: related } : { kind: 'mentioned', ticker: related };
}

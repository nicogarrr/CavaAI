/**
 * Representación del titular de noticias (quick win UX 4): los titulares
 * de display generados por CavaAI (metadata.headline_from_source ===
 * false, p.ej. «AAPL 8-K presentado ante la SEC») llevan el ticker como
 * prefijo legado F175; cuando la superficie ya muestra el ticker en su
 * propia columna/campo, el prefijo se omite para no pintarlo dos veces.
 * NUNCA se recorta un titular real de la fuente (verbatim), aunque
 * empiece por el ticker: ahí el texto es de la fuente y se respeta.
 */

/**
 * Devuelve el título a pintar junto a un ticker visible aparte.
 * Solo recorta el prefijo «TICKER » cuando headlineFromSource === false
 * (flag persistido en metadata por la ingesta / el script de saneado).
 */
export function newsDisplayTitle(
    title: string,
    ticker: string | null | undefined,
    headlineFromSource: boolean | null | undefined,
): string {
    return stripTickerPrefix(untokenizeHeadline(title), ticker, headlineFromSource);
}

/**
 * Algunos titulares llegan de la fuente (GDELT) tokenizados con espacios
 * alrededor de la puntuación: «AST SpaceMobile , Inc . ( ASTS )». Solo al
 * PINTAR se recoloca la puntuación («AST SpaceMobile, Inc. (ASTS)»); el texto
 * guardado sigue siendo el verbatim de la fuente (procedencia).
 */
export function untokenizeHeadline(title: string): string {
    return title
        .replace(/\s+([,.;:!?])(?=\s|$)/g, '$1')
        .replace(/\(\s+/g, '(')
        .replace(/\s+\)/g, ')')
        .replace(/[ \t]{2,}/g, ' ');
}

function stripTickerPrefix(
    title: string,
    ticker: string | null | undefined,
    headlineFromSource: boolean | null | undefined,
): string {
    if (headlineFromSource !== false || !ticker) return title;
    const normalizedTicker = ticker.trim().toUpperCase();
    if (!normalizedTicker) return title;
    const trimmed = title.trimStart();
    if (!trimmed.toUpperCase().startsWith(`${normalizedTicker} `)) return title;
    return trimmed.slice(normalizedTicker.length + 1);
}

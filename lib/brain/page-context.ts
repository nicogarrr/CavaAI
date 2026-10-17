/**
 * Contexto de página explícito para el cerebro global (pastilla "Viendo X").
 *
 * El ticker viaja como TEXTO: la Company se resuelve en el backend dentro
 * del catálogo global; el contenido privado posterior se aísla por tenant.
 * El cliente nunca manda IDs de base de datos.
 */
export type BrainPageContext = {
    path: string;
    label: string | null;
    ticker: string | null;
};

const SECTION_LABELS: Array<[RegExp, string]> = [
    [/^\/inicio/, 'Inicio'],
    [/^\/portfolio/, 'Cartera'],
    [/^\/watchlist/, 'Seguimiento'],
    [/^\/knowledge/, 'Biblioteca'],
    [/^\/inversores/, 'Inversores'],
    [/^\/temas/, 'Temas'],
    [/^\/propicks/, 'ProPicks'],
    [/^\/calendar/, 'Calendario'],
    [/^\/macro-calendar/, 'Calendario macro'],
    [/^\/screener/, 'Screener'],
    [/^\/discover/, 'Descubrir'],
    [/^\/cuellos/, 'Cuellos de botella'],
    [/^\/alerts/, 'Alertas'],
    [/^\/plan/, 'Plan'],
    [/^\/risk/, 'Riesgo'],
    [/^\/taxes/, 'Impuestos'],
    [/^\/security/, 'Seguridad'],
];

const TICKER_RE = /^[A-Z0-9.\-]{1,20}$/;

/** Deriva el contexto de la ruta actual; null si la página no es identificable. */
export function brainPageContext(pathname: string | null): BrainPageContext | null {
    if (!pathname) return null;
    const research = pathname.match(/^\/research\/([A-Za-z0-9.\-]{1,20})(?:\/|$)/);
    if (research) {
        const ticker = research[1].toUpperCase();
        if (TICKER_RE.test(ticker)) {
            return { path: pathname, label: ticker, ticker };
        }
    }
    const stocks = pathname.match(/^\/stocks\/([A-Za-z0-9.\-]{1,20})(?:\/|$)/);
    if (stocks) {
        const ticker = stocks[1].toUpperCase();
        if (TICKER_RE.test(ticker)) {
            return { path: pathname, label: ticker, ticker };
        }
    }
    for (const [pattern, label] of SECTION_LABELS) {
        if (pattern.test(pathname)) {
            return { path: pathname, label, ticker: null };
        }
    }
    return null;
}

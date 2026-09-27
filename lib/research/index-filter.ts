/**
 * F308: el índice de research pintaba las ~2115 empresas del registro en una
 * sola página (HTML enorme, sin filtro ni paginación). El filtro por texto y
 * la paginación se resuelven en el servidor desde searchParams (?q=, ?page=)
 * y este helper concentra la lógica para probarla de verdad.
 *
 * El tamaño de página casa con el tope de detalle de tesis del índice: cada
 * fila visible pide su snapshot en la llamada batch, así ninguna tarjeta
 * visible sale sin su detalle por recorte silencioso.
 */
export const RESEARCH_INDEX_PAGE_SIZE = 40;

export type ResearchIndexItem = {
    ticker: string;
    name: string;
};

/** Filtro por ticker o nombre, sin distinción de mayúsculas. */
export function filterResearchIndex<T extends ResearchIndexItem>(items: T[], query: string): T[] {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
        (item) => item.ticker.toLowerCase().includes(q) || (item.name ?? '').toLowerCase().includes(q),
    );
}

export type ResearchIndexSlice<T> = {
    /** Filas de la página pedida (ya acotada al rango válido). */
    rows: T[];
    /** Página efectiva, 1-based y acotada entre 1 y `pages`. */
    page: number;
    /** Número total de páginas (al menos 1, aunque no haya filas). */
    pages: number;
    /** Coincidencias tras el filtro. */
    total: number;
    /** Posición 1-based de la primera fila visible (0 si no hay filas). */
    from: number;
    /** Posición de la última fila visible (inclusive). */
    to: number;
};

export function paginateResearchIndex<T>(
    items: T[],
    requestedPage: number,
    pageSize: number = RESEARCH_INDEX_PAGE_SIZE,
): ResearchIndexSlice<T> {
    const total = items.length;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    const page = Math.min(Math.max(1, requestedPage), pages);
    const start = (page - 1) * pageSize;
    const rows = items.slice(start, start + pageSize);
    return { rows, page, pages, total, from: total === 0 ? 0 : start + 1, to: start + rows.length };
}

/** searchParams.page llega como string; cualquier cosa rara cae a la página 1. */
export function parseIndexPage(raw: string | undefined): number {
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 1;
}

/** Enlace del índice conservando el filtro; página 1 sin filtro vuelve a la URL limpia. */
export function researchIndexHref(query: string, page: number): string {
    const params = new URLSearchParams();
    const q = query.trim();
    if (q) params.set('q', q);
    if (page > 1) params.set('page', String(page));
    const qs = params.toString();
    return qs ? `/research?${qs}` : '/research';
}

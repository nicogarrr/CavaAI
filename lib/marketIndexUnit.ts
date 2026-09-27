/**
 * F152: un nivel de índice no es dinero. La unidad la declara el backend
 * (`unit` en /api/market/indices), pero respuestas viejas/cacheadas no la
 * traen: normalizamos por símbolo conocido. Un símbolo desconocido sin
 * `unit` devuelve null - el front lo pinta como número plano, sin asumir
 * USD (no inventamos una unidad que el proveedor no declara).
 */
export type MarketIndexUnit = 'index' | 'usd';

const KNOWN_UNITS: Record<string, MarketIndexUnit> = {
    '^GSPC': 'index',
    '^IXIC': 'index',
    'BTC-USD': 'usd',
    'GC=F': 'usd',
    'SI=F': 'usd',
};

export function marketIndexUnit(symbol: string, unit?: string | null): MarketIndexUnit | null {
    if (unit === 'index' || unit === 'usd') return unit;
    // Los índices de Yahoo llevan prefijo «^»: sin `unit`, es nivel de índice.
    if (symbol.startsWith('^')) return 'index';
    return KNOWN_UNITS[symbol] ?? null;
}

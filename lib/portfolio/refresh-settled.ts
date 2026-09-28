/**
 * Partición de los resultados allSettled del refresco de precios:
 * - updated: la escritura PATCH llegó al backend;
 * - skipped: el proveedor no devolvió cotización (ni se intentó escribir);
 * - failed: la escritura se intentó y falló (red/5xx).
 * Con Promise.all, un fallo de B rechazaba todo aunque A ya se hubiera
 * guardado: la caché no se invalidaba y el usuario no sabía qué pasó.
 */
export type SettledRefresh =
    | { status: 'fulfilled'; value: { symbol: string; written: boolean } }
    | { status: 'rejected'; reason?: unknown };

export function partitionSettledRefreshes(
    symbols: string[],
    settled: SettledRefresh[],
): { updated: string[]; skipped: string[]; failed: string[] } {
    const updated: string[] = [];
    const skipped: string[] = [];
    const failed: string[] = [];
    settled.forEach((result, index) => {
        if (result.status === 'rejected') {
            failed.push(symbols[index]);
        } else if (result.value.written) {
            updated.push(result.value.symbol);
        } else {
            skipped.push(result.value.symbol);
        }
    });
    return { updated, skipped, failed };
}

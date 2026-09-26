/**
 * Carga compartida de las acciones populares del buscador (Ctrl+K).
 *
 * Hay varias instancias de SearchCommand (desktop, icono movil, drawer): si
 * cada una cacheara por su cuenta, abrir dos superficies repetiria la rafaga
 * de llamadas Finnhub. Este modulo mantiene UNA promesa en vuelo y UN
 * resultado cacheado a nivel de aplicacion:
 *
 * - Exito: el resultado (incluida la lista vacia honesta) se cachea y las
 *   aperturas siguientes no refetchean.
 * - Fallo: la promesa en vuelo se descarta, asi que la siguiente apertura
 *   REINTENTA (un cierre a mitad de carga o un error de red no dejan el
 *   buscador muerto hasta remount).
 */

/**
 * Resultado tipado del fetch: `ok` incluye la lista vacia VALIDA (sin clave
 * Finnhub configurada, universo vacio); `error` es fallo de proveedor/red y
 * NUNCA se cachea: la proxima apertura reintenta y la UI puede avisar.
 */
export type PopularStocksResult =
    | { status: "ok"; stocks: StockWithWatchlistStatus[] }
    | { status: "error" };

type Fetcher = () => Promise<PopularStocksResult>;

let cached: StockWithWatchlistStatus[] | null = null;
let inflight: Promise<StockWithWatchlistStatus[]> | null = null;

export function loadPopularStocks(
    fetcher: Fetcher,
): Promise<StockWithWatchlistStatus[]> {
    if (cached !== null) return Promise.resolve(cached);
    if (!inflight) {
        inflight = fetcher()
            .then((result) => {
                if (result.status !== "ok") {
                    // Fallo de proveedor: no cachear; la proxima apertura
                    // reintenta (nunca queda como lista vacia permanente).
                    inflight = null;
                    throw new Error("popular_stocks_fetch_failed");
                }
                cached = result.stocks;
                inflight = null;
                return cached;
            })
            .catch((error: unknown) => {
                // No cachear fallos: la proxima apertura reintenta.
                inflight = null;
                throw error;
            });
    }
    return inflight;
}

/** Solo para tests: reinicia la cache del modulo. */
export function _resetPopularStocksForTests(): void {
    cached = null;
    inflight = null;
}

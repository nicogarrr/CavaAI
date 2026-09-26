/**
 * Redaccion de credenciales en URLs, para mensajes de error y logs.
 *
 * Modulo puro y sin dependencias a proposito: lo necesitan todos los clientes
 * de upstream (finnhub, alpha vantage, FMP, twelve data, polygon) y asi queda
 * testeable de forma aislada.
 *
 * Los vendors de mercado llevan la clave en la query (?token=, ?apikey=) y
 * tanto fetch como httpx meten la URL completa en el texto de sus errores, de
 * modo que sin esto la key del servidor llegaba al navegador y al log.
 */

/** Parametros de query que nunca deben aparecer en un mensaje o log. */
export const SECRET_QUERY_KEYS = [
    'token',
    'apikey',
    'api_key',
    'access_token',
    'key',
    'c',
    'sig',
    'signature',
] as const;

/** Sustituye por REDACTED los valores de los parametros de credencial. */
export function redactUrl(rawUrl: string): string {
    let url: URL;
    try {
        url = new URL(rawUrl);
    } catch {
        // Si ni siquiera es una URL absoluta, no hay query que limpiar.
        return rawUrl;
    }
    let changed = false;
    for (const key of SECRET_QUERY_KEYS) {
        if (url.searchParams.has(key)) {
            url.searchParams.set(key, 'REDACTED');
            changed = true;
        }
    }
    return changed ? url.toString() : rawUrl;
}

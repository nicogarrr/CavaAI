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

/** Pares clave=valor de credencial en texto libre (tracebacks, logs). */
const SECRET_QUERY_RE = new RegExp(
    `\\b(${SECRET_QUERY_KEYS.join('|')})=([^\\s&"'<>]+)`,
    'gi',
);

/** Credenciales en userinfo de URL (esquema://usuario:password@host). */
const USERINFO_RE = /(\b[a-z][a-z0-9+.-]*:\/\/[^/\s:@]+):([^@\s/]+)@/gi;

/**
 * Redacta credenciales en cualquier texto: userinfo de URL y pares
 * clave=valor de query. Un traceback de httpx/fetch lleva la URL completa
 * del proveedor, y un DSN de Redis/Postgres lleva la password en el
 * userinfo: los dos caminos metian el secreto del servidor en logs y
 * respuestas.
 */
export function redactSecretsInText(text: string): string {
    return text
        .replace(USERINFO_RE, '$1:REDACTED@')
        .replace(SECRET_QUERY_RE, '$1=REDACTED');
}

/** Sustituye por REDACTED los valores de los parametros de credencial. */
export function redactUrl(rawUrl: string): string {
    let url: URL;
    try {
        url = new URL(rawUrl);
    } catch {
        // Una entrada que ni siquiera es una URL absoluta NUNCA vuelve
        // intacta al error: es texto arbitrario que puede llevar
        // credenciales (una URL truncada conserva su ?token=...).
        return '[invalid URL]';
    }
    let changed = false;
    for (const key of SECRET_QUERY_KEYS) {
        if (url.searchParams.has(key)) {
            url.searchParams.set(key, 'REDACTED');
            changed = true;
        }
    }
    if (url.password) {
        url.password = 'REDACTED';
        changed = true;
    }
    return changed ? url.toString() : rawUrl;
}

/**
 * Copia superficial de un error con el mensaje redactado, para encadenarlo
 * como causa sin arrastrar la URL cruda: fetch rechaza con la URL completa
 * (?token=...) en message/cause, y un console.error del error de frontera
 * volcaba esa cadena entera al log. Se conserva el `name` (el tipo) porque
 * es lo unico del original que ayuda a diagnosticar. Lo que no es Error ni
 * string puede llevar la URL en cualquier campo: se descarta.
 */
export function sanitizeCause(error: unknown): unknown {
    if (error instanceof Error) {
        const clean = new Error(redactSecretsInText(error.message));
        clean.name = error.name;
        return clean;
    }
    if (typeof error === 'string') {
        return redactSecretsInText(error);
    }
    return undefined;
}

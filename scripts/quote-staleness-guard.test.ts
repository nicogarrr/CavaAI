import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const finnhubActions = readFileSync('lib/actions/finnhub.actions.ts', 'utf8');

// F358 (reporte de usuario, 28/09): BN mostraba 36,87 (+0,66%) cuando el
// mercado marcaba 36,43 (-1,19%): la cotizacion de la sesion ANTERIOR se
// servia como actual. Causa: fetchJSON usa force-cache + revalidate; con
// errores sostenidos del proveedor (429 por cuota, F357) Next sirve el
// ultimo valor bueno indefinidamente (stale-while-error) y el fetch
// resuelve 200 con el dato viejo, sin que el error llegue al catch. La
// unica senal de frescura es el timestamp `t` de la cotizacion.
test('F358: la cotizacion Finnhub se valida por su propio timestamp antes de aceptarla', () => {
    assert.match(finnhubActions, /STALE_QUOTE_MAX_AGE_SECONDS\s*=\s*24 \* 3600/, 'tolerancia de 24h definida');
    assert.match(finnhubActions, /data\.t/, 'se lee el timestamp t de la cotizacion');
    assert.match(finnhubActions, /ageSeconds\s*<=\s*STALE_QUOTE_MAX_AGE_SECONDS/, 'se compara la edad con la tolerancia');
});

test('F358: el rechazo por obsoleta cae al fallback (backend Yahoo) o a null, nunca se devuelve como actual', () => {
    const fnStart = finnhubActions.indexOf('async function fetchStockQuote');
    const fnEnd = finnhubActions.indexOf('export type EarningsEvent');
    assert.ok(fnStart > 0 && fnEnd > fnStart);
    const body = finnhubActions.slice(fnStart, fnEnd);
    const guardPos = body.indexOf('ageSeconds <= STALE_QUOTE_MAX_AGE_SECONDS');
    const fallbackPos = body.indexOf('FMP_BACKEND_URL');
    assert.ok(guardPos > 0 && fallbackPos > guardPos, 'el fallback existe despues del guard de frescura');
    assert.match(body, /return null;/, 'miss honesto si todo falla');
});

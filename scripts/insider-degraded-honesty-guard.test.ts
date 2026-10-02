/**
 * F234: /insider?ticker=AAPL mostraba «AAPL: degraded» a pelo — un estado
 * técnico opaco. El backend devuelve filings_scanned/filings_failed/reason:
 * degraded se explica con cabecera común + números, la reason es detalle
 * opcional (nunca sustituto), y queda claro que no es «sin actividad».
 * Partial muestra las señales reales con aviso de cobertura y su vacío no
 * cuenta como «analizados» filings que fallaron.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { analyzedCountCopy, degradedCopy, durableReadCopy } from '../lib/insider-status-copy.ts';

const view = readFileSync('components/insider/InsiderSignalsView.tsx', 'utf8');
const count = (v: unknown) => String(v);

test('degraded con contadores: cabecera con N de M y sin reason', () => {
    const { header, detail } = degradedCopy('AAPL', { filings_scanned: 20, filings_failed: 20 }, count);
    assert.equal(header, 'AAPL: SEC EDGAR no devolvió ningún Form 4 legible (20 con error de 20 escaneados).');
    assert.equal(detail, null);
});

test('degraded con reason (catch global): cabecera que abarca consulta y lectura + reason como detalle', () => {
    // El catch también cubre fallos antes de consultar Form 4 (CIK, listado):
    // afirmar «no devolvió ningún Form 4 legible» sobreafirmaría.
    const { header, detail } = degradedCopy('AAPL', { reason: 'TypeError: fetch failed' }, count);
    assert.equal(header, 'AAPL: no se pudieron consultar o leer las señales Form 4 de SEC EDGAR.');
    assert.equal(detail, 'TypeError: fetch failed');
});

test('la reason nunca sustituye a la cabecera en el componente', () => {
    assert.match(view, /degradedCopy\(initialTicker, initialResult, countText\)\.header/);
    assert.match(view, /Es un fallo\s+de lectura, no una ausencia de actividad insider\. Reintenta más tarde\./);
    assert.match(view, /Detalle técnico:/);
    assert.ok(
        !/\{initialTicker\}: \{formatRecordValue\(initialResult\.reason \?\? initialResult\.status\)\}/.test(view),
        'la salida cruda reason ?? status queda vetada',
    );
});

test('partial sin señales: legibles de escaneados, nunca «analizados» inflado', () => {
    assert.equal(
        analyzedCountCopy('partial', { filings_scanned: 20, filings_parsed: 13 }, count),
        '13 legibles de 20 escaneados',
    );
    assert.equal(analyzedCountCopy('ok', { filings_scanned: 20 }, count), '20 analizados');
});

test('partial muestra las señales con aviso de cobertura incompleta', () => {
    assert.match(view, /initialResult\.status === 'partial' \?/);
    assert.match(view, /lectura incompleta/);
    assert.match(view, /cubren solo los filings legibles/);
});

test('el vacío usa analyzedCountCopy (consciente del estado)', () => {
    assert.match(view, /analyzedCountCopy\(initialResult\.status, initialResult, countText\)/);
});

test('unavailable afirma solo lo probado: sin CIK en EDGAR (backend: insider_service devuelve unavailable solo sin CIK)', () => {
    assert.match(view, /no es un emisor SEC\s+estadounidense \(sin CIK en EDGAR\), así\s+que no tiene señales insider Form 4/);
    assert.ok(
        !/no constan Form 4 registrados/.test(view),
        '«no constan Form 4 registrados» no queda probado por unavailable',
    );
    // La reason estable del backend («not a US SEC filer») ya la dice la
    // cabecera; solo una reason distinta se muestra como detalle.
    assert.match(view, /initialResult\.reason !== 'not a US SEC filer'/);
});

/* ------------------------------------------------------------------ *
 * Lectura DURABLE (GET /api/insider/filings). No va a EDGAR: consulta *
 * la tabla de filings persistidos por el monitor. Antes el panel    *
 * pintaba «Monitor cada 15 min · 0 filings persistidos» +           *
 * «lectura durable no disponible (OperationalError)»: un cero de    *
 * «no se pudo leer» disfrazado de recuento y una razón cruda a pelo.*
 * ------------------------------------------------------------------ */

test('lectura durable: el 0 de un status no-ok es «desconocido», no un recuento', () => {
    const copy = durableReadCopy({ reason: 'OperationalError' });
    assert.match(copy.header, /número es\s+desconocido y no cero/);
    assert.match(copy.header, /es un fallo de esa lectura, no una ausencia de Form 4/);
    assert.match(copy.header, /Las señales de\s+arriba se leen de SEC EDGAR directamente y no dependen de ese histórico/);
    assert.equal(copy.detail, 'OperationalError');
    assert.equal(durableReadCopy({}).detail, null);
});

test('el panel usa durableReadCopy y no muestra el count si el status no es ok', () => {
    assert.ok(!/lectura durable no disponible/.test(view), 'el copy crudo de status/reason queda vetado');
    assert.match(view, /durableReadCopy\(initialFilings\)/);
    assert.match(view, /initialFilings && initialFilings\.status === 'ok' \?/);
    // Con status no-ok el número NO se pinta como recuento.
    assert.match(view, /número de filings persistidos desconocido/);
    assert.ok(
        !/countText\(initialFilings\?\.count \?\? 0\)/.test(view),
        'el count de una lectura fallida no puede salir como número',
    );
    assert.match(view, /Detalle técnico: \{durable\.detail\}/);
});

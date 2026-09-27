/**
 * F234: /insider?ticker=AAPL mostraba «AAPL: degraded» a pelo — un estado
 * técnico opaco sin explicación ni reintento. El backend ya devuelve
 * filings_scanned/filings_failed/reason: un estado así se explica con sus
 * números, nunca con la palabra cruda. Y un «degraded» (nada legible) no es
 * un «sin actividad insider»: el copy debe decirlo. Partial muestra las
 * señales reales parseadas con su aviso de cobertura, no las esconde.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const view = readFileSync('components/insider/InsiderSignalsView.tsx', 'utf8');

test('degraded se explica con los contadores del backend, no con la palabra cruda', () => {
    const degraded = view.slice(view.indexOf("initialResult.status === 'degraded'"));
    assert.match(degraded, /filings_failed/);
    assert.match(degraded, /filings_scanned/);
    assert.match(degraded, /no una ausencia de actividad insider/);
    assert.match(degraded, /Reintenta más tarde/);
});

test('la palabra «degraded» cruda nunca es el mensaje', () => {
    assert.ok(
        !/formatRecordValue\(initialResult\.reason \?\? initialResult\.status\)\}\s*\n?\s*\{initialResult\.status === 'unavailable'/.test(view) ||
        view.includes("initialResult.status === 'degraded' ?"),
        'el fallback reason ?? status no puede ser la única salida de degraded',
    );
});

test('partial muestra las señales con aviso de cobertura incompleta', () => {
    assert.match(view, /initialResult\.status === 'partial' \?/);
    assert.match(view, /lectura incompleta/);
    assert.match(view, /cubren solo los filings legibles/);
});

test('unavailable mantiene su explicación propia (no emisor SEC US)', () => {
    assert.match(view, /no es un emisor SEC estadounidense/);
});

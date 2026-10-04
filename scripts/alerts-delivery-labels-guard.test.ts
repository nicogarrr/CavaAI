/**
 * F20/B21: /alerts mostraba «in_app: sin registro» y estados crudos
 * (delivered/failed). Etiquetas ES; lo desconocido se muestra tal cual.
 * Ejecución: node --experimental-strip-types --test scripts/alerts-delivery-labels-guard.test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { etiquetaCanal, etiquetaEstadoEntrega } from '../lib/alerts/delivery-labels.ts';

test('canal y estado de entrega en español, desconocido tal cual', () => {
    assert.equal(etiquetaCanal('in_app'), 'en la app');
    assert.equal(etiquetaEstadoEntrega('delivered'), 'entregada');
    assert.equal(etiquetaEstadoEntrega('failed'), 'fallida');
    assert.equal(etiquetaEstadoEntrega('sin registro'), 'sin registro de entrega');
    assert.equal(etiquetaCanal('sms'), 'sms');
    assert.equal(etiquetaEstadoEntrega('raro'), 'raro');
});

test('AlertsManager pinta canal y estado con las etiquetas, no los valores internos', () => {
    const src = readFileSync('components/alerts/AlertsManager.tsx', 'utf8');
    assert.match(src, /\{channelText\}: \{statusText\}/);
    assert.doesNotMatch(src, /\{channel\}: \{status\}/);
});

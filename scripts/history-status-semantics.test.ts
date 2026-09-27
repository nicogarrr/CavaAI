/**
 * Tests semánticos del estado de la tarjeta «Historial de precio · 1 año»
 * (F161): la insignia describe la serie, no la cotización puntual. Sin
 * velas es «no disponible» aunque haya quote; con pocas sesiones es
 * «parcial» y la UI muestra el tramo disponible con aviso.
 * Ejecución: node --experimental-strip-types --test scripts/history-status-semantics.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { marketHistoryStatus, HISTORY_PARTIAL_MIN_SESSIONS } from '../lib/market/history-status.ts';

void test('sin sesiones es «no disponible», nunca «parcial» (caso BRK.B: quote sin velas)', () => {
    assert.equal(marketHistoryStatus(0), 'unavailable');
    assert.equal(marketHistoryStatus(Number.NaN), 'unavailable');
    assert.equal(marketHistoryStatus(-3), 'unavailable');
});

void test('pocas sesiones es «parcial»', () => {
    assert.equal(marketHistoryStatus(1), 'partial');
    assert.equal(marketHistoryStatus(HISTORY_PARTIAL_MIN_SESSIONS - 1), 'partial');
});

void test('serie completa es «disponible»', () => {
    assert.equal(marketHistoryStatus(HISTORY_PARTIAL_MIN_SESSIONS), 'available');
    assert.equal(marketHistoryStatus(252), 'available');
});

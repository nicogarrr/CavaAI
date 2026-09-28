/**
 * Tarjeta de índices con resultado PROPIO discriminado (datos/error):
 *  - getMarketIndicesResult devuelve { data, error } y getMarketIndices es
 *    solo un envoltorio; el fallo ya no se pliega a [] en silencio.
 *  - La tarjeta decide «desconectado» con indicesResult.error, NO con el
 *    error de la petición vecina (screener): cada ruta puede caer sola.
 * Ejecución: node --experimental-strip-types --test scripts/indices-card-state-guard.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
// Node (strip-types) exige la extension .ts en runtime; tsc la rechaza
// sin allowImportingTsExtensions. El guard se ejecuta con node, no con tsc.
// @ts-expect-error - import runtime de node
import { indicesCardState } from '../lib/market/indices-card-state.ts';

const here = dirname(fileURLToPath(import.meta.url));
const source = (rel: string) => readFileSync(join(here, '..', rel), 'utf8');

void test('índices caídos con screener operativo: la tarjeta dice desconectado', () => {
    const state = indicesCardState(0, new Error('fetch failed'), () => true);
    assert.equal(state, 'unavailable');
});

void test('índices operativos con screener caído: la tarjeta pinta datos', () => {
    // Dirección contraria: el error del vecino no entra en la decisión.
    const state = indicesCardState(3, null, () => true);
    assert.equal(state, 'data');
});

void test('petición completada y lista vacía: lectura honesta de mercado sin datos', () => {
    const state = indicesCardState(0, null, () => false);
    assert.equal(state, 'empty');
});

void test('un 4xx no es "desconectado" aunque la lista venga vacía', () => {
    const state = indicesCardState(0, new Error('HTTP 404'), () => false);
    assert.equal(state, 'empty');
});

void test('la acción expone un resultado discriminado y el wrapper legacy', () => {
    const actions = source('lib/actions/market.actions.ts');
    assert.ok(actions.includes('getMarketIndicesResult'), 'variante discriminada presente');
    assert.ok(actions.includes('return { data, error: null };'), 'éxito discriminado');
    assert.ok(actions.includes('return { data: [], error };'), 'fallo discriminado, ya no traga a []');
});

void test('la página decide la tarjeta con el error propio de índices', () => {
    const page = source('app/(root)/screener/page.tsx');
    assert.ok(page.includes('getMarketIndicesResult()'), 'la página pide el resultado discriminado');
    assert.ok(page.includes('indicesCardState(validIndices.length, indicesResult.error'), 'estado desde el error PROPIO');
    assert.ok(!page.includes('isBackendUnavailableError(screenerError);\n  // Un indice'), 'la tarjeta ya no infiere del screener');
});

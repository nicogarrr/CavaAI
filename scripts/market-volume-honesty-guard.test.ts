/**
 * Guard F318: un volumen desconocido nunca se fabrica como 0.
 * Backend: /api/market/candles conserva null; frontend: el análisis técnico
 * promedia solo sesiones con volumen conocido y no aparenta estadística con
 * datos insuficientes (0/0 incluido).
 * Ejecución: node --experimental-strip-types --test scripts/market-volume-honesty-guard.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
// @ts-expect-error TS5097
import { volumeTrendStats } from '../lib/market/volume-trend.ts';

void test('comportamiento: los huecos no entran en las medias y los 0 reales sí', () => {
    const base = [...Array.from({ length: 20 }, () => 1000), ...Array.from({ length: 20 }, () => 1250)];
    const stats = volumeTrendStats(base);
    assert.ok(stats && stats.avgVolume > 0 && stats.volumeTrend === 'increasing');
    // Huecos intercalados: se ignoran; la media se calcula con los conocidos.
    const conHuecos = base.map((volume, index) => (index % 3 === 0 ? null : volume));
    const statsHuecos = volumeTrendStats(conHuecos);
    assert.ok(statsHuecos && statsHuecos.avgVolume > 0);
    // Un 0 REAL (sesión conocida sin volumen) cuenta como dato, no se borra.
    const conCeroReal = [...Array.from({ length: 20 }, () => 1000), ...Array.from({ length: 20 }, () => 0)];
    const statsCero = volumeTrendStats(conCeroReal);
    assert.ok(statsCero && statsCero.avgVolume === 0);
});

void test('comportamiento: sin datos suficientes o ventana previa en 0 no hay tendencia aparentada', () => {
    assert.equal(volumeTrendStats([100, 200, null, 300]), null, 'pocos datos conocidos -> null');
    assert.equal(volumeTrendStats(Array.from({ length: 40 }, () => null)), null);
    // 19 conocidas: sin ventana reciente completa, no hay ni media.
    assert.equal(volumeTrendStats(Array.from({ length: 19 }, () => 1000)), null);
    // 20 conocidas: media sí, tendencia no (falta la segunda ventana).
    const veinte = volumeTrendStats(Array.from({ length: 20 }, () => 1000));
    assert.ok(veinte && veinte.avgVolume === 1000 && veinte.volumeTrend === null);
    // 21-39 conocidas: la ventana previa incompleta NUNCA se compara contra
    // la reciente de 20 (19 null + 1 conocida no puede dar 'increasing').
    const treintaNueve = volumeTrendStats([...Array.from({ length: 19 }, () => null), 1250, ...Array.from({ length: 20 }, () => 1250)]);
    assert.ok(treintaNueve && treintaNueve.volumeTrend === null);
    const previaCero = [...Array.from({ length: 20 }, () => 0), ...Array.from({ length: 20 }, () => 500)];
    const stats = volumeTrendStats(previaCero);
    assert.ok(stats && stats.volumeTrend === null, '0/0 evitado: sin tendencia cuando la base es 0');
});

void test('estructura: el backend conserva null y el frontend tipa huecos', () => {
    const market = readFileSync('data-engine/app/api/routes/market.py', 'utf8');
    assert.ok(!market.includes('else 0.0)'), 'ningún volumen se fabrica como 0.0 en market.py');
    const finnhub = readFileSync('lib/actions/finnhub.actions.ts', 'utf8');
    assert.match(finnhub, /v: \(number \| null\)\[\]/);
    assert.match(finnhub, /volumeTrendStats\(volumes\)/);
    const workspace = readFileSync('lib/actions/market-workspace.actions.ts', 'utf8');
    assert.match(workspace, /normalizeChartCandles\(candles,/);
    assert.match(readFileSync('lib/market/normalize-chart.ts', 'utf8'), /volume: candles\.v\?\.\[index\] \?\? null/);
});

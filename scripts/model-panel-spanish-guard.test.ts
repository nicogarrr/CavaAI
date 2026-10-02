/**
 * Guard: el panel del modelo a largo plazo y la oportunidad de mercado no
 * muestran identificadores en ingles/snake_case al usuario (regla de UI en espanol).
 *
 * Ejecutar: node --experimental-strip-types --test scripts/model-panel-spanish-guard.test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const panel = readFileSync('components/research/FundamentalModelPanels.tsx', 'utf8');
const page = readFileSync('app/(root)/research/[ticker]/page.tsx', 'utf8');
const labels = readFileSync('lib/research/metric-labels.ts', 'utf8');

test('drivers, KPIs y entradas faltantes pasan por metricLabel', () => {
    assert.match(panel, /revenue_drivers\.map\(termLabel\)/);
    assert.match(panel, /kpis\.map\(termLabel\)/);
    assert.match(panel, /missing_inputs\.map\(termLabel\)/);
    assert.match(page, /formula\.missing_inputs\.map\(termLabel\)/);
});

test('no queda «Value/share» en la UI y unknown/low/high tienen etiqueta en espanol', () => {
    assert.doesNotMatch(panel, /Value\/share/);
    assert.doesNotMatch(page, /Value\/share/);
    assert.match(page, /unknown: 'desconocido'/);
    assert.match(page, /low: 'baja'/);
});

test('las entradas de modelo mas habituales tienen etiqueta', () => {
    for (const key of ['traceable_wacc', 'organic_growth', 'share_count', 'working_capital', 'monthly_arpu']) {
        assert.ok(labels.includes(`${key}:`), key);
    }
});

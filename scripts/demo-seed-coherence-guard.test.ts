/**
 * Guarda de coherencia de la maqueta demo (F139/F140): aunque las cifras DEMO
 * se declaran ficticias, lo que se muestra como calculo debe ser internamente
 * coherente.
 *  - Cada check del foso declara su unidad: el formato no puede depender de
    passed (un valor no-tasa salia como «42.000,0 %»).
 *  - El margen de seguridad se deriva de los escenarios mostrados; no puede
 *    ser un literal incoherente (22 % cuando (51-42)/51 = 17,6 %).
 * Ejecución: node --experimental-strip-types --test scripts/demo-seed-coherence-guard.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const landing = readFileSync(join(here, '..', 'components/landing/PublicLanding.tsx'), 'utf8');

void test('cada check del foso declara unidad y el formato no depende de passed', () => {
    const moatBlock = landing.slice(landing.indexOf('const demoMoat'), landing.indexOf('];', landing.indexOf('const demoMoat')));
    const checks = moatBlock.match(/\{ check:/g) ?? [];
    const units = moatBlock.match(/unit: '/g) ?? [];
    assert.ok(checks.length > 0, 'demoMoat encontrado');
    assert.equal(units.length, checks.length, 'todo check declara unit');
    assert.ok(!/check\.passed\s*\?\s*formatPercent/.test(landing), 'el formato no se elige por passed');
    assert.ok(landing.includes("check.unit === 'rate'"), 'el formato se elige por unidad');
    assert.ok(!moatBlock.includes('value: 420'), 'sin valores sin unidad clara (420 era el 42.000 %)');
});

void test('el margen de seguridad demo se deriva de los escenarios', () => {
    assert.ok(!/marginOfSafety:\s*0\.\d+/.test(landing), 'margen de seguridad sin literal incoherente');
    assert.ok(landing.includes('24 * 0.25 + 51 * 0.5 + 78 * 0.25'), 'derivacion visible junto a los escenarios');
    // Coherencia numerica: (51 - 42) / 51 = 17,6 %
    const expected = (24 * 0.25 + 51 * 0.5 + 78 * 0.25 - 42) / (24 * 0.25 + 51 * 0.5 + 78 * 0.25);
    assert.ok(Math.abs(expected - 0.1765) < 0.001, 'la derivacion da 17,6 %');
});

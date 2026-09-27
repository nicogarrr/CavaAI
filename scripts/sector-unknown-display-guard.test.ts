/**
 * F106: /research mostraba «Unknown · Unknown» en tarjetas de empresas sin
 * clasificación (ALM, A3M - el master guarda la cadena 'Unknown'). 'Unknown'
 * es ausencia de dato: se omite la parte sin dato o se declara «Sector sin
 * dato», nunca se muestra el placeholder en inglés.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { sectorIndustryLine } from '../lib/sector-display.ts';

const index = readFileSync('app/(root)/research/page.tsx', 'utf8');
const ticker = readFileSync('app/(root)/research/[ticker]/page.tsx', 'utf8');

test('Unknown en ambos campos: «Sector sin dato», nunca el placeholder', () => {
    assert.equal(sectorIndustryLine('Unknown', 'Unknown'), 'Sector sin dato');
    assert.equal(sectorIndustryLine(null, null), 'Sector sin dato');
    assert.equal(sectorIndustryLine('', ''), 'Sector sin dato');
});

test('variantes del placeholder (espacios, capitalización) también son ausencia', () => {
    assert.equal(sectorIndustryLine(' unknown ', 'UNKNOWN'), 'Sector sin dato');
    assert.equal(sectorIndustryLine(' Unknown ', 'Unknown'), 'Sector sin dato');
    assert.equal(sectorIndustryLine(' Health Care ', 'Unknown'), 'Health Care');
});

test('valores reales pasan intactos; la parte Unknown se omite', () => {
    assert.equal(sectorIndustryLine('Health Care', 'Pharmaceuticals'), 'Health Care · Pharmaceuticals');
    assert.equal(sectorIndustryLine('Health Care', 'Unknown'), 'Health Care');
    assert.equal(sectorIndustryLine('Unknown', 'Pharmaceuticals'), 'Pharmaceuticals');
});

test('índice y ficha componen la línea con sectorIndustryLine', () => {
    assert.match(index, /sectorIndustryLine\(company\.sector, company\.industry\)/);
    assert.match(ticker, /sectorIndustryLine\(company\.sector, company\.industry\)/);
    assert.ok(!/\{company\.sector\} · \{company\.industry\}/.test(ticker), 'la cabecera de la ficha aún concatena en crudo');
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const overview = readFileSync('components/PersonalizedOverview.tsx', 'utf8');

test('F300: las tarjetas de alerta de /inicio enlazan al contexto de la alerta', () => {
    // El enlace va a la investigación del ticker REAL del disparo (nunca una
    // ruta inventada): se pinta solo cuando item.ticker existe.
    assert.match(overview, /\{item\.ticker && \(/);
    assert.match(overview, /href=\{`\/research\/\$\{item\.ticker\}`\}/);
    assert.match(overview, /Abrir investigación de \{item\.ticker\}/);
});

test('F300: si hay documento fuente también se enlaza', () => {
    assert.match(overview, /\{item\.sourceUrl && \(/);
    assert.match(overview, /Abrir documento fuente/);
});

test('F300: el enlace es alcanzable al tacto (min-h 44px)', () => {
    const block = overview.slice(overview.indexOf('Abrir investigación de') - 600);
    assert.match(block, /min-h-\[44px\]/);
});

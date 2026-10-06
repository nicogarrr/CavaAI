/** Inversores: cobertura PARTIAL del 13F visible (nunca se muestran cifras dudosas sin aviso). */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const ficha = readFileSync('app/(root)/inversores/[slug]/page.tsx', 'utf8');
const carteras = readFileSync('app/(root)/inversores/carteras/page.tsx', 'utf8');
const actions = readFileSync('lib/actions/investors.actions.ts', 'utf8');

test('el tipo de inversor lleva coverage', () => {
    assert.match(actions, /coverage\?: string \| null/);
});

test('la ficha avisa de datos parciales cuando coverage es partial', () => {
    assert.match(ficha, /investor\.coverage === 'partial'/);
    assert.match(ficha, /Datos parciales: el total guardado no cuadra/);
});

test('las carteras marcan "Datos parciales" en la tarjeta', () => {
    assert.match(carteras, /investor\.coverage === 'partial'/);
    assert.match(carteras, /Datos parciales/);
});

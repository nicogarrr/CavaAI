/**
 * F204: en el indice de research, nombre y sector·industria se truncan
 * visualmente con line-clamp-1. Todo texto truncado visualmente necesita
 * un title con el contenido completo: sin el, un usuario visual no tiene
 * forma de recuperar lo oculto (el lector de pantalla si lo lee del DOM).
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync('app/(root)/research/page.tsx', 'utf8');

test('el nombre truncado conserva el texto completo en title', () => {
    assert.match(page, /line-clamp-1[^>]*title=\{company\.name\}/);
});

test('sector·industria truncado conserva el texto completo en title', () => {
    assert.match(page, /line-clamp-1[^>]*title=\{sectorLine\}/);
    assert.match(page, /const sectorLine =/);
});

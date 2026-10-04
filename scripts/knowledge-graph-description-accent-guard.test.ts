/** Copy visible del detalle de nodo del grafo: «descripción» con tilde. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('el aviso de descripción ausente lleva tilde', () => {
    const source = readFileSync('lib/knowledge-graph/graph-model.ts', 'utf8');
    assert.ok(source.includes('El grafo no guarda descripción para este tipo de nodo.'));
    assert.ok(!source.includes('no guarda descripcion'));
});

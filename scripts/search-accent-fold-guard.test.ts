/**
 * El buscador de acciones pliega diacríticos antes de consultar al proveedor:
 * «Telefónica» y «Diseño Textil» no devolvían resultados (el índice no lleva
 * acentos). No añade datos: solo cambia cómo se escribe la consulta.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { foldSearchQuery } from '../lib/search-query.ts';

test('quita acentos y la eñe, y colapsa espacios', () => {
    assert.equal(foldSearchQuery('Telefónica'), 'Telefonica');
    assert.equal(foldSearchQuery('  Industria de Diseño   Textil '), 'Industria de Diseno Textil');
    assert.equal(foldSearchQuery('AAPL'), 'AAPL');
    assert.equal(foldSearchQuery('SAN.MC'), 'SAN.MC');
});

test('el buscador usa la consulta plegada', () => {
    const src = readFileSync('lib/actions/finnhub.actions.ts', 'utf8');
    assert.match(src, /foldSearchQuery\(query\)/);
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync('app/(root)/knowledge-graph/page.tsx', 'utf8');

test('F312: Confianza y Procedencia no quedan pegadas en la tabla de relaciones', () => {
    // Confianza va alineada a la derecha y Procedencia a la izquierda: sin
    // padding horizontal los dos textos se tocaban en el borde compartido
    // («CONFIANZAPROCEDENCIA») a cualquier ancho (confirmado 1440 y 1920).
    assert.match(page, /px-3 py-2 text-right" scope="col">Confianza/);
    assert.match(page, /py-2 pl-3" scope="col">Procedencia/);
    assert.match(page, /px-3 py-3 text-right text-gray-400">\{formatConfidence\(edge\.confidence\)/);
    assert.match(page, /py-3 pl-3 text-xs text-gray-500">\{edge\.provenance\}/);
});

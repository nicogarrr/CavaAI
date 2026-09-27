import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const overview = readFileSync('components/PersonalizedOverview.tsx', 'utf8');

test('F326: el importe del hero de /inicio no deja el simbolo de divisa solo', () => {
    // A 768px la fila valor+bloque de G/P estrangulaba el importe y
    // break-words lo partia dejando el «€» (unido por NBSP) en su propia
    // linea: la fila ahora envuelve el bloque de G/P debajo y el cuerpo
    // crece por tramos (xl -> 2xl -> 3xl) antes de romper.
    assert.match(overview, /min-\[420px\]:flex-row min-\[420px\]:flex-wrap min-\[420px\]:justify-between/);
    assert.match(overview, /break-words text-xl font-bold text-white sm:text-2xl xl:text-3xl/);
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync('app/(root)/research/settings/page.tsx', 'utf8');

test('F324: el badge de conector no se sale de la tarjeta a 768px', () => {
    // La fila etiqueta+badge en tarjetas de media columna desbordaba:
    // la etiqueta necesita min-w-0/break-words y el badge shrink-0.
    assert.match(page, /flex min-w-0 items-center gap-2/);
    assert.match(page, /break-words font-semibold text-gray-200">\{meta\?\.label \?\? key\}/);
    assert.match(page, /shrink-0 rounded-full border px-2 py-0\.5/);
});

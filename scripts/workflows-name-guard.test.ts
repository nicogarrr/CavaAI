import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync('app/(root)/research/workflows/page.tsx', 'utf8');

test('F329: el nombre del workflow (token largo irrompible) envuelve a 360px', () => {
    // GenerateThesisWorkflow y similares no tienen puntos de corte: sin
    // break-all salían recortados de la tarjeta a 360px.
    assert.match(page, /min-w-0 break-all font-semibold text-gray-100">\{workflow\.name\}/);
});

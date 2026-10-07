import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
const src = readFileSync('app/(root)/watchlist/page.tsx', 'utf8');
test('la fecha de cierre móvil se puede leer completa, sin elipsis', () => {
 const date = src.match(/<dd className="([^"]+)"[^>]*>\{stock\.priceAsOf[^\n]+/);
 assert.ok(date, 'fecha de cierre móvil existe');
 assert.ok(!date[1].split(/\s+/).includes('truncate'), 'una fecha es procedencia financiera, no texto decorativo');
 assert.match(date[1], /break-words/);
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
const page = readFileSync('app/(root)/inversores/mas-compradas/page.tsx', 'utf8');
test('más compradas pagina sin eliminar fechas, procedencia ni compradores', () => {
    assert.match(page, /paginate\(data\.items, pagina, PAGE_SIZE\)/);
    assert.match(page, /paged\.items\.map/);
    assert.doesNotMatch(page, /data\.items\.map/);
    assert.match(page, /<Pagination basePath="\/inversores\/mas-compradas" page=\{paged\.page\} total=\{paged\.total\}/);
    assert.match(page, /data\.report_dates/);
    assert.match(page, /item\.buyers\.map/);
    assert.match(page, /item\.cusip/);
});
test('el nombre del emisor completo es legible en móvil', () => {
    assert.match(page, /break-words text-base font-medium text-gray-100">\{item\.name_of_issuer\}/);
    assert.match(page, /flex flex-col items-start justify-between gap-3 sm:flex-row/);
    assert.doesNotMatch(page, /truncate text-base/);
});

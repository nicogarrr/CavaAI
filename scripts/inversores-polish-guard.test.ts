/** Inversores pulido: migas legibles, "1 nueva", enlaces en fila y paginacion dentro de la pagina. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const read = (path: string) => readFileSync(path, 'utf8');
const crumbs = read('components/layout/Breadcrumbs.tsx');
const grid = read('app/(root)/inversores/page.tsx');
const portfolios = read('app/(root)/inversores/carteras/page.tsx');
const bought = read('app/(root)/inversores/mas-compradas/page.tsx');
const ficha = read('app/(root)/inversores/[slug]/page.tsx');
const pagination = read('app/(root)/inversores/_components/Pagination.tsx');

test('las migas no muestran el slug crudo de las subpaginas de Inversores', () => {
    assert.match(crumbs, /'mas-compradas': 'Más compradas'/);
    assert.match(crumbs, /'carteras': 'Carteras'/);
    assert.match(crumbs, /humanizeSlug/);
});

test('singular "nueva" cuando hay una sola', () => {
    assert.match(bought, /new_count === 1 \? 'nueva' : 'nuevas'/);
});

test('los enlaces de la cabecera van en una fila', () => {
    assert.match(grid, /flex flex-wrap items-center gap-x-6/);
});

test('rejilla, carteras y ficha paginan dentro de la pagina, sin scroll infinito', () => {
    for (const source of [grid, portfolios, ficha]) {
        assert.match(source, /paginate\(/);
        assert.match(source, /<Pagination/);
    }
    assert.match(pagination, /Página \{page\} de \{total\}/);
    assert.ok(!/IntersectionObserver|infinite/i.test(pagination + grid + portfolios));
});

test('la ficha conserva la vista al cambiar de pagina', () => {
    assert.match(ficha, /params=\{\{ vista: 'posiciones' \}\}/);
    assert.match(ficha, /params=\{\{ vista: 'cambios' \}\}/);
});

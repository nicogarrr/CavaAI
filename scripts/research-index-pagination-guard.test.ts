/**
 * Guarda F308: el índice de research pintaba las ~2115 empresas del registro
 * en una sola página, sin filtro ni paginación (HTML enorme y todo el detalle
 * por encima del tope salía «pendiente»). Ahora filtra (?q=) y pagina
 * (?page=) en servidor, con contador honesto de lo visible.
 *
 * Los tests ejercitan el helper real (lib/research/index-filter.ts) y
 * comprueban que la página lo usa de verdad, no solo que contiene strings.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
    filterResearchIndex,
    paginateResearchIndex,
    parseIndexPage,
    RESEARCH_INDEX_PAGE_SIZE,
    researchIndexHref,
    // @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
} from '../lib/research/index-filter.ts';

const PAGE = 'app/(root)/research/page.tsx';

function readSource(path: string): string {
    return readFileSync(path, 'utf8');
}

void test('el filtro encuentra por ticker o nombre sin distinguir mayúsculas', () => {
    const items = [
        { ticker: 'AAPL', name: 'Apple Inc.' },
        { ticker: 'MSFT', name: 'Microsoft Corporation' },
        { ticker: 'ITX.MC', name: 'Industria de Diseño Textil, S.A.' },
    ];
    assert.deepEqual(filterResearchIndex(items, 'apple').map((i) => i.ticker), ['AAPL']);
    assert.deepEqual(filterResearchIndex(items, 'mc').map((i) => i.ticker), ['ITX.MC']);
    assert.deepEqual(filterResearchIndex(items, '  ').length, 3, 'filtro vacío no filtra');
    assert.deepEqual(filterResearchIndex(items, 'zzz'), [], 'sin coincidencias da lista vacía');
});

void test('la paginación acota la página y cuenta lo visible de verdad', () => {
    const items = Array.from({ length: 95 }, (_, i) => ({ ticker: `T${i}`, name: `Empresa ${i}` }));
    const first = paginateResearchIndex(items, 1);
    assert.equal(first.rows.length, RESEARCH_INDEX_PAGE_SIZE);
    assert.deepEqual([first.from, first.to, first.total, first.pages], [1, RESEARCH_INDEX_PAGE_SIZE, 95, 3]);
    const last = paginateResearchIndex(items, 3);
    assert.equal(last.rows.length, 95 - 2 * RESEARCH_INDEX_PAGE_SIZE);
    assert.equal(last.to, 95);
    const outOfRange = paginateResearchIndex(items, 99);
    assert.equal(outOfRange.page, 3, 'una página fuera de rango cae en la última, nunca en una página vacía');
    assert.equal(outOfRange.rows.length, last.rows.length);
    const empty = paginateResearchIndex([], 4);
    assert.deepEqual([empty.from, empty.to, empty.pages, empty.rows.length], [0, 0, 1, 0]);
});

void test('parseIndexPage y los enlaces conservan el filtro sin inventar parámetros', () => {
    assert.equal(parseIndexPage('2'), 2);
    assert.equal(parseIndexPage('0'), 1);
    assert.equal(parseIndexPage('-3'), 1);
    assert.equal(parseIndexPage('abc'), 1);
    assert.equal(parseIndexPage(undefined), 1);
    assert.equal(researchIndexHref('', 1), '/research');
    assert.equal(researchIndexHref('apple', 1), '/research?q=apple');
    assert.equal(researchIndexHref('apple', 3), '/research?q=apple&page=3');
    assert.equal(researchIndexHref('', 2), '/research?page=2');
});

void test('la página usa el helper y declara el contador honesto de lo visible', () => {
    const page = readSource(PAGE);
    assert.match(page, /filterResearchIndex\(ordered, query\)/, 'filtra en servidor con el helper');
    assert.match(page, /paginateResearchIndex\(filtered, requestedPage\)/, 'pagina en servidor con el helper');
    assert.match(page, /const detailed = slice\.rows\.slice\(0, THESIS_DETAIL_LIMIT\)/, 'el detalle se pide solo para la página visible');
    assert.match(page, /THESIS_DETAIL_LIMIT = RESEARCH_INDEX_PAGE_SIZE/, 'toda tarjeta visible entra en el tope de detalle');
    assert.ok(!page.includes('pendiente'), 'desaparece el estado «pendiente»: ninguna tarjeta visible sale sin detalle por recorte');
    assert.match(page, /Mostrando \$\{formatNumber\(slice\.from\)\}-\$\{formatNumber\(slice\.to\)\} de \$\{formatNumber\(slice\.total\)\} empresas/, 'contador de lo visible');
    assert.match(page, /coincidencias para «\$\{query\}» \(de \$\{formatNumber\(ordered\.length\)\} empresas en el registro\)/, 'contador del filtro contra el total real');
    assert.match(page, /Página \{formatNumber\(slice\.page\)\} de \{formatNumber\(slice\.pages\)\}/, 'posición de página declarada');
});

void test('el buscador es un formulario GET accesible y las coincidencias vacías son honestas', () => {
    const page = readSource(PAGE);
    assert.match(page, /<form action="\/research"[^>]*method="get">/, 'filtro por GET: la URL cuenta el estado');
    assert.match(page, /htmlFor="research-index-q"/, 'label asociado al input');
    assert.match(page, /Sin coincidencias para «\$\{query\}»\./, 'filtro sin resultados lo dice, no pinta un índice fantasma');
    assert.match(page, /Quitar (el )?filtro/, 'salida explícita del filtro');
});

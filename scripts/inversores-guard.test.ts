/**
 * Modulo Inversores (PR 1): copy honesto y nav. Sin datos no se inventan cifras,
 * Daily Journal no es "cartera de Munger" y el valor sale en dolares compactos.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const grid = readFileSync('app/(root)/inversores/page.tsx', 'utf8');
const portfolios = readFileSync('app/(root)/inversores/carteras/page.tsx', 'utf8');
const detail = readFileSync('app/(root)/inversores/[slug]/page.tsx', 'utf8');
const format = readFileSync('app/(root)/inversores/_components/format.ts', 'utf8');
const constants = readFileSync('lib/constants.ts', 'utf8');

test('quien no presenta 13F dice "Sin datos" en la rejilla y en la ficha', () => {
    assert.match(grid, /Sin datos: no presenta 13F/);
    assert.match(detail, /Sin datos: no presenta 13F/);
});

test('cada pagina cita la fuente (SEC 13F) y el retardo de 45 días', () => {
    for (const source of [grid, portfolios, detail]) {
        assert.match(source, /SEC, Form 13F \(EDGAR\)/);
        assert.match(source, /45 días/);
    }
});

test('el valor se muestra como dólares compactos desde miles de dólares', () => {
    assert.match(format, /formatMarketCapUsd\(thousands \* 1000\)/);
});

test('ninguna pagina etiqueta una cartera como cartera de Munger', () => {
    for (const source of [grid, portfolios, detail]) {
        assert.ok(!/cartera de Munger/i.test(source));
    }
});

test('la ficha no muestra tickers (el 13F solo trae CUSIP y emisor)', () => {
    assert.ok(!/\.ticker|\.symbol/.test(detail));
});

test('Inversores tiene entrada de nav una sola vez', () => {
    const tree = constants.slice(constants.indexOf('export const NAV_SECTIONS'), constants.indexOf('export function flattenNavItems'));
    assert.equal(tree.split("href: '/inversores'").length - 1, 1);
});

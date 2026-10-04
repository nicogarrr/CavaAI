/**
 * F6 (continuación de #828): el bloque «Detalle avanzado» sale de la misma
 * serie indicativa que el TWR cuando twr_is_exact=false (anualizado,
 * volatilidad, Sortino, VaR/CVaR, Calmar y Beta usan portfolio_returns en
 * portfolio_intelligence_service). Cada tarjeta lleva el mismo aviso.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync('app/(root)/portfolio/intelligence/page.tsx', 'utf8');

for (const [exact, indicative] of [
    ['Anualizado', 'Anualizado indicativo'],
    ['Volatilidad', 'Volatilidad indicativa'],
    ['Sortino', 'Sortino indicativo'],
    ['VaR 95%', 'VaR 95% indicativo'],
    ['CVaR 95%', 'CVaR 95% indicativo'],
    ['Calmar', 'Calmar indicativo'],
    ['Beta', 'Beta indicativa'],
]) {
    test(`${exact} se rotula indicativo cuando el TWR no es exacto`, () => {
        assert.ok(page.includes(`twr_is_exact ? '${exact}' : '${indicative}'`));
    });
}

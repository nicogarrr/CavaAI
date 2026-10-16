import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const overview = readFileSync('components/PersonalizedOverview.tsx', 'utf8');
const breakdown = readFileSync('components/portfolio/PortfolioValueBreakdown.tsx', 'utf8');

test('F326: el importe del hero de /inicio no deja el simbolo de divisa solo', () => {
    // El valor vive ahora en un desglose: una columna hasta420px y dos despues.
    // Cada celda puede encoger y el neto crece solo desde sm, sin un bloque
    // de G/P que estrangule su ancho. Mantiene moneda base y tamaño movil.
    assert.match(overview, /<PortfolioValueBreakdown summary=\{portfolioSummary\} \/>/);
    assert.match(breakdown, /grid grid-cols-1 gap-3 min-\[420px\]:grid-cols-2/);
    assert.match(breakdown, /<div className="min-w-0">/);
    assert.match(breakdown, /break-words text-xl font-bold text-white sm:text-2xl/);
    assert.match(breakdown, /formatMoney\(totalValue, baseCurrency\)/);
});

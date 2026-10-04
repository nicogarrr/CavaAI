/**
 * F15: /insider arrancaba vacío hasta escribir un ticker. Ahora ofrece
 * atajos de solo lectura con la cartera (cantidad != 0) y la watchlist, sin
 * duplicados ni tickers inventados.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { buildInsiderShortcuts } from '../lib/insider/shortcuts.ts';

test('cartera sin posiciones cerradas y watchlist sin repetir cartera', () => {
    const result = buildInsiderShortcuts(
        [
            { symbol: 'aapl', quantity: 3 },
            { symbol: 'MSFT', quantity: 0 },
            { symbol: ' aapl ', quantity: 1 },
        ],
        [{ symbol: 'AAPL' }, { symbol: 'nvda' }, { symbol: '' }],
    );
    assert.deepEqual(result, { portfolio: ['AAPL'], watchlist: ['NVDA'] });
});

test('sin datos no inventa atajos', () => {
    assert.deepEqual(buildInsiderShortcuts(null, undefined), { portfolio: [], watchlist: [] });
});

test('la página y la vista usan los atajos', () => {
    const page = readFileSync('app/(root)/insider/page.tsx', 'utf8');
    const view = readFileSync('components/insider/InsiderSignalsView.tsx', 'utf8');
    assert.match(page, /buildInsiderShortcuts\(portfolioSummary\?\.holdings, watchlist\)/);
    assert.match(view, /De tu cartera/);
    assert.match(view, /De tu watchlist/);
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

test('Alertas: enlaces de tarjeta con objetivo tactil de 44 px', () => {
    const src = read('components/alerts/AlertsManager.tsx');
    assert.doesNotMatch(src, /className="text-xs text-teal-400 hover:text-teal-300 hover:underline"/);
    assert.match(src, /inline-flex min-h-\[44px\] items-center text-xs text-teal-400/);
});

test('Cartera: tickers de la distribucion con objetivo tactil de 44 px', () => {
    const src = read('components/portfolio/PortfolioAllocation.tsx');
    assert.match(src, /min-h-\[44px\] min-w-\[44px\] items-center text-sm text-gray-300/);
});

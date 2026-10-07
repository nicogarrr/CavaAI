import assert from 'node:assert/strict';
import test from 'node:test';
// @ts-expect-error Node type stripping requires the extension.
import { cleanBars, dailyPivots, sma, adx, structure, fibonacci, rangeBars } from '../lib/market/technical.ts';
const bars = Array.from({ length: 60 }, (_, i) => ({ date: new Date(Date.UTC(2026, 0, i + 1)).toISOString().slice(0, 10), open: 100 + i, high: 102 + i, low: 99 + i, close: 101 + i, volume: null }));
test('pivots use the observed last bar and no quote', () => {
    const levels = dailyPivots([{ date: '2026-01-01', open: 10, high: 15, low: 9, close: 12, volume: null }]);
    assert.deepEqual(levels.map((v) => v.price), [18, 15, 9, 6]);
    assert.deepEqual(dailyPivots([{ date: '2026-01-01', close: 12, volume: null }]), []);
});
test('ADX Wilder requires 28 bars, rejects missing or impossible OHLC, bounded 0..100', () => {
    assert.equal(adx(bars.slice(0, 27)), null);
    assert.equal(adx(bars.slice(0, 28)), 100);
    assert.equal(adx(bars), 100);
    assert.equal(adx(bars.map((v) => ({ ...v, high: null }))), null);
    assert.equal(adx(bars.map((v) => ({ ...v, low: 1000 }))), null);
    const flat = bars.map((v) => ({ ...v, open: 100, close: 100, high: 100, low: 100 }));
    assert.equal(adx(flat), 0);
});
test('SMA and structure use complete lookback, not fabricated history', () => {
    assert.equal(sma(bars.slice(0, 49), 50), null);
    assert.equal(sma(bars, 50), 135.5);
    assert.equal(structure(bars), 'Alcista');
    assert.equal(structure(bars.slice(0, 19)), 'Sin datos');
    assert.equal(structure(bars.map((v) => ({ ...v, high: null }))), 'Sin datos');
});
test('Fibonacci is the range high-low, requires complete OHLC', () => {
    assert.equal(fibonacci(bars).length, 5);
    assert.equal(fibonacci(bars)[2].price, (99 + 161) / 2);
    assert.deepEqual(fibonacci(bars.map((v) => ({ ...v, high: null }))), []);
});
test('clean series sorts/dedupes and rejects impossible dates and prices', () => {
    assert.equal(cleanBars([...bars, bars[0]]).length, 60);
    assert.deepEqual(cleanBars([{ ...bars[0], date: '2026-02-31' }, { ...bars[0], close: NaN }, { ...bars[0], close: -1 }]), []);
    assert.equal(rangeBars(bars, '1M').length, 32);
    assert.equal(rangeBars(bars, 'YTD').length, 60);
});

test('company header replaces sparkline and composes technical workspace once', async () => {
    const { readFileSync } = await import('node:fs');
    const header = readFileSync('components/research/CompanyHeaderQuote.tsx', 'utf8');
    const page = readFileSync('app/(root)/research/[ticker]/page.tsx', 'utf8');
    assert.match(header, /CompanyTechnicalWorkspace snapshot=\{snapshot\}/);
    assert.doesNotMatch(header, /<polyline/);
    assert.doesNotMatch(page, /<CompanyMarketPanel/);
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
// @ts-expect-error Node type stripping requires extension.
import { chartRequestWindow, intradayWindow, isChartRange, CHART_RANGES } from '../lib/market/chart-ranges.ts';
test('all eight reference ranges and strict rejection', () => {
    assert.equal(CHART_RANGES.length, 8);
    for (const range of CHART_RANGES) assert.equal(isChartRange(range), true);
    for (const value of ['1Y', '30', null, {}, 'MAX']) assert.equal(isChartRange(value), false);
});
test('hourly data for short ranges, full history for Max', () => {
    assert.equal(chartRequestWindow('1D', 1900000000).resolution, '60');
    assert.equal(chartRequestWindow('5D', 1900000000).resolution, '60');
    assert.equal(chartRequestWindow('5A', 1900000000).resolution, 'D');
    assert.equal(chartRequestWindow('Máx', 1900000000).from, 0);
    assert.equal(chartRequestWindow('5A', 1900000000).to - chartRequestWindow('5A', 1900000000).from, 5 * 366 * 86400);
});
test('hourly series preserve timestamps, rolling windows never fake sessions', () => {
    const bars = Array.from({ length: 150 }, (_, i) => ({ timestamp: 1700000000 + i * 3600 }));
    assert.equal(intradayWindow(bars, '1D').length, 24);
    assert.equal(intradayWindow(bars, '5D').length, 120);
    assert.deepEqual(intradayWindow([], '1D'), []);
});
test('server action gates auth and verified listing; no naked ticker fallback', () => {
    const action = readFileSync('lib/actions/company-chart.actions.ts', 'utf8');
    assert.match(action, /await requireAuthenticatedUser\(\)/);
    assert.match(action, /quoteSymbolFor\(company, ticker\)/);
    assert.match(action, /if \(!symbol\) return empty/);
    assert.match(action, /isE2EMarketFixtureEnabled\(process\.env, ticker\)/);
    assert.match(action, /getCandles\(symbol,/);
});

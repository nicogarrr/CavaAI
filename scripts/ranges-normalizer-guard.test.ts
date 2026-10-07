import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
test('range action delegates real candles to the same daily OHLC boundary', () => {
    const source = readFileSync('lib/actions/company-chart.actions.ts', 'utf8');
    assert.match(source, /import \{ normalizeChartCandles, type CompanyChartBar \} from '@\/lib\/market\/normalize-chart'/);
    assert.match(source, /const bars = normalizeChartCandles\(candles, window\)/);
    assert.match(source, /intradayWindow\(bars, range\) : bars/);
    assert.doesNotMatch(source, /candles\.t\.forEach|hasOHLC|byTimestamp/);
});

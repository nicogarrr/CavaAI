import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { overallocatedDimension } from '../lib/plan/target-totals.ts';

test('editing sector 100% and asset class 100% is valid, including ticker 100%', () => {
    const existing = [
        { kind: 'sector', target_pct: 100, label: 'Technology', band_pct: 7 },
        { kind: 'asset_class', target_pct: 100, label: 'equity', band_pct: 10 },
        { kind: 'ticker', target_pct: 100, label: 'ASTS', band_pct: 0 },
    ];
    assert.equal(overallocatedDimension(existing), null);
});

test('rejects totals over 100 only within the same dimension', () => {
    assert.deepEqual(overallocatedDimension([
        { kind: 'sector', target_pct: 60 },
        { kind: 'sector', target_pct: 50 },
        { kind: 'asset_class', target_pct: 100 },
    ]), { kind: 'sector', total: 110 });
    assert.deepEqual(overallocatedDimension([
        { kind: 'asset_class', target_pct: 101 },
    ]), { kind: 'asset_class', total: 101 });
    assert.deepEqual(overallocatedDimension([
        { kind: 'ticker', target_pct: 90 }, { kind: 'ticker', target_pct: 20 },
    ]), { kind: 'ticker', total: 110 });
});

test('accepts empty and zero targets and decimal rounding at 100%', () => {
    assert.equal(overallocatedDimension([]), null);
    assert.equal(overallocatedDimension([{ kind: 'sector', target_pct: 0 }]), null);
    assert.equal(overallocatedDimension(Array.from({ length: 10 }, () => ({ kind: 'ticker', target_pct: 10.000000000000002 }))), null);
});

test('submit uses dimension validation rather than a cross-dimension total', () => {
    const source = readFileSync('components/plan/PlanSetupDialog.tsx', 'utf8');
    assert.match(source, /overallocatedDimension\(allocations\)/);
    assert.doesNotMatch(source, /totalPct/);
});

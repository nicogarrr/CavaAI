import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

test('ProPicks mobile tablist is bounded so overflow scrolls inside instead of growing offscreen', () => {
    const source = readFileSync('components/proPicks/ProPicksTabs.tsx', 'utf8');
    const list = source.match(/<TabsList[\s\S]*?<\/TabsList>/)?.[0];
    assert.ok(list);
    for (const token of ['w-full', 'min-w-0', 'max-w-full', 'justify-start', 'overflow-x-auto']) assert.ok(list.includes(token), token);
    assert.ok(!list.includes('w-max'));
    assert.ok(!list.includes('min-w-full'));
    assert.ok(list.includes('tabIndex={0}'));
    assert.ok(list.includes('Paper trading'));
});

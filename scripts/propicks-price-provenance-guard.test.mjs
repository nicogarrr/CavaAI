import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
const adapter = readFileSync('lib/actions/propicks-funnel.actions.ts', 'utf8');
const content = readFileSync('components/proPicks/EnhancedProPicksContent.tsx', 'utf8');
test('ProPicks no llama actual a un cierre persistido ni inventa USD', () => {
    assert.match(adapter, /priceAsOf: c\.price_as_of \?\? undefined/);
    assert.match(adapter, /priceCurrency: c\.currency \|\| undefined/);
    assert.match(content, /pick\.currentPrice > 0 && pick\.priceAsOf && pick\.priceCurrency/);
    assert.match(content, /formatPrice\(pick\.currentPrice, pick\.priceCurrency\)/);
    assert.match(content, /Precio registrado · \{formatUserDate\(pick\.priceAsOf\)\}/);
    assert.doesNotMatch(content, /Precio actual|formatPrice\(pick\.currentPrice, 'USD'\)/);
});

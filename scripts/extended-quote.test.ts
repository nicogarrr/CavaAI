import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
// @ts-expect-error explicit extension required by node strip-types.
import { extendedQuoteLabel } from '../lib/market/extended-quote.ts';
const base = { source: 'Yahoo Finance (no oficial), retraso posible', ticker: 'MSFT', status: 'available' as const, session: 'post' as const, price_session: 'post' as const, price: 103, timestamp: 1791497100, trading_date: '2026-10-08', fetched_at: 1791497100 };
test('Madrid times and explicit sessions including DST', () => {
    assert.equal(extendedQuoteLabel(base), 'Post-cierre · 00:05');
    assert.equal(extendedQuoteLabel({ ...base, session: 'pre', price_session: 'pre' }), 'Premercado · 00:05');
    assert.equal(extendedQuoteLabel({ ...base, session: 'regular', price_session: 'regular' }), 'Mercado abierto · 00:05');
    assert.equal(extendedQuoteLabel({ ...base, session: 'cerrado' }), 'Último post-cierre del 8 oct · 00:05');
    assert.match(extendedQuoteLabel({ ...base, status: 'retrasado' }), /Retrasado$/);
    assert.equal(extendedQuoteLabel({ ...base, timestamp: 1798761600 }), 'Post-cierre · 01:00');
});
test('no timestamp, price, or provider means N/D', () => {
    for (const q of [null, { ...base, timestamp: null }, { ...base, price: null }, { ...base, status: 'unavailable' as const }, { ...base, session: 'cerrado' as const, trading_date: null }]) {
        assert.equal(extendedQuoteLabel(q), 'N/D');
    }
});
test('visible-only 60s refresh and no stale/error or undated metric fallback', () => {
    const ui = readFileSync('components/research/CompanyHeaderQuote.tsx', 'utf8');
    assert.match(ui, /document.visibilityState !== 'visible'/);
    assert.match(ui, /setInterval\([\s\S]*60000\)/);
    assert.match(ui, /setQuote\(null\); \/\/ No stale-on-error/);
    assert.match(ui, /previous_close_timestamp \? quote.previous_close : null/);
    assert.doesNotMatch(ui, /snapshot.quote|Precio de fecha desconocida/);
    assert.match(ui, /quoteSymbolFor/);
});

test('price_session prevents last regular point becoming premarket or post becoming regular close', () => {
    assert.equal(extendedQuoteLabel({ ...base, session: 'pre', price_session: 'regular' }), 'Último precio regular del 8 oct · 00:05');
    assert.equal(extendedQuoteLabel({ ...base, session: 'cerrado', price_session: 'regular', regular_close_timestamp: base.timestamp }), 'Cierre del 8 oct · 00:05');
    assert.equal(extendedQuoteLabel({ ...base, price_session: null }), 'N/D');
});

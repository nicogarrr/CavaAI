/**
 * Quick win UX 5: badges «En cartera / En watchlist» en noticias y movers.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { tickerBadgesFor, TICKER_BADGE_LABELS } from '../lib/ticker-badges.ts';

const news = readFileSync('app/(root)/research/news/page.tsx', 'utf8');
const movers = readFileSync('app/(root)/movers/page.tsx', 'utf8');
const action = readFileSync('lib/actions/ticker-context.actions.ts', 'utf8');

test('la pertenencia se calcula por ticker normalizado', () => {
    const portfolio = new Set(['COST']);
    const watchlist = new Set(['NFLX']);
    assert.deepEqual(tickerBadgesFor('cost', portfolio, watchlist), ['portfolio']);
    assert.deepEqual(tickerBadgesFor('NFLX', portfolio, watchlist), ['watchlist']);
    assert.deepEqual(tickerBadgesFor('AAPL', portfolio, watchlist), []);
    assert.deepEqual(tickerBadgesFor('COST', new Set(['COST']), new Set(['COST'])), ['portfolio', 'watchlist']);
    assert.equal(TICKER_BADGE_LABELS.portfolio, 'En cartera');
    assert.equal(TICKER_BADGE_LABELS.watchlist, 'En watchlist');
});

test('la lectura degrada a conjuntos vacíos, nunca a badges fabricados', () => {
    assert.match(action, /\.catch\(\(\) => \[\] as Array<\{ ticker: string \}>\)/);
    assert.match(action, /\.catch\(\(\) => \[\] as Array<\{ symbol: string \}>\)/);
});

test('noticias y movers componen los badges junto al ticker', () => {
    for (const src of [news, movers]) {
        assert.match(src, /getTickerContext\(\)/);
        assert.match(src, /<TickerContextBadges/);
    }
    // En noticias, solo cuando hay ticker (los eventos macro no llevan).
    assert.match(news, /\{event\.ticker \? \(/);
    // En movers, las tres tablas reciben el contexto.
    assert.equal((movers.match(/tickerSets=\{tickerSets\}/g) ?? []).length, 3);
});

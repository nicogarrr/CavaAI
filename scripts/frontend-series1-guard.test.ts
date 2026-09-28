import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const read = (p: string) => readFileSync(p, 'utf8');

test('news table keeps five decision columns and a contextual disclosure', () => {
  const src = read('app/(root)/research/news/page.tsx');
  for (const column of ['Ticker', 'Fecha', 'Titular', 'Materialidad', 'Estado y detalle']) assert.match(src, new RegExp(`scope="col">${column}`));
  assert.doesNotMatch(src, /scope="col">Peso al evaluar|scope="col">Impacto|scope="col">¿Actualizar\?/);
  assert.match(src, /Ver contexto/);
});

test('desktop portfolio and watchlist keep destructive action within symbol menu', () => {
  const portfolio = read('components/portfolio/PortfolioHoldings.tsx');
  const watchlist = read('app/(root)/watchlist/page.tsx');
  assert.doesNotMatch(portfolio, /<TableHead[^>]*>Fiscal<\/TableHead>|<TableHead[^>]*>Acciones<\/TableHead>/);
  assert.doesNotMatch(watchlist, /<TableHead[^>]*>Acciones<\/TableHead>/);
  assert.match(portfolio, /<summary[^>]*Opciones/);
  assert.match(portfolio, /handleDelete\(holding.symbol\)/);
  assert.match(watchlist, /<summary[^>]*Opciones/);
  assert.match(watchlist, /<WatchlistRemoveButton symbol=\{stock.symbol\}/);
});

test('volume belongs to most-active movers only and screener has units', () => {
  const movers = read('app/(root)/movers/page.tsx');
  assert.match(movers, /showVolume \? <th/);
  assert.match(movers, /caption="Mayor volumen" tickerSets=\{tickerSets\} showVolume/);
  const screener = read('app/(root)/screener/page.tsx');
  assert.match(screener, /B US\$/);
  assert.match(screener, /screenerMarketCap\(r.marketCap\)/);
});

/**
 * Guard F152 (unidad falsa en índices): un nivel de índice no es dinero.
 * Antes, /screener pintaba «S&P 500 7743,41 US$» y «Nasdaq 27.068,72 US$»
 * (FRED etiqueta esas series como «Units: Index»), y /inicio les ponía el
 * símbolo monetario vía formatMoney. El backend etiqueta cada serie con
 * unit ("index" | "usd") y el front formatea según esa unidad: índices sin
 * sufijo monetario, US$ solo en Bitcoin/Oro/Plata.
 *
 * Ejecucion: node --experimental-strip-types --test scripts/market-index-units-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const route = readFileSync('data-engine/app/api/routes/market.py', 'utf8');
const screener = readFileSync('app/(root)/screener/page.tsx', 'utf8');
const overview = readFileSync('components/PersonalizedOverview.tsx', 'utf8');

describe('market index units guard (F152)', () => {
  it('el backend etiqueta índices como unit "index" y metales/cripto como "usd"', () => {
    assert.match(route, /\{"symbol": "\^GSPC", "name": "S&P 500", "unit": "index"\}/, '^GSPC con unit index');
    assert.match(route, /\{"symbol": "\^IXIC", "name": "Nasdaq Composite", "unit": "index"\}/, '^IXIC con unit index');
    assert.match(route, /\{"symbol": "BTC-USD", "name": "Bitcoin", "unit": "usd"\}/, 'BTC con unit usd');
  });

  it('/screener formatea por unidad, no pinta US$ en todo', () => {
    assert.equal(screener.includes("formatPrice(i.price, 'USD')}"), false, 'sin formato US$ incondicional');
    assert.match(screener, /i\.unit === 'index'/, 'rama por unidad presente');
  });

  it('/inicio formatea por unidad y propaga unit al estado', () => {
    assert.match(overview, /index\.unit === 'index'/, 'rama por unidad presente');
    assert.match(overview, /unit: data\.unit/, 'unit llega al estado');
  });
});

/**
 * Guard F152 (unidad falsa en índices): un nivel de índice no es dinero.
 * El backend etiqueta cada serie con unit ("index" | "usd") y el front
 * formatea según esa unidad: US$ solo cuando unit === "usd"; índices y
 * series sin unidad conocida van como número plano. Las respuestas legacy
 * sin unit se normalizan por símbolo conocido (marketIndexUnit), nunca
 * asumiendo USD - ese fallback volvía a pintar «US$» en el S&P 500.
 *
 * Ejecucion: node --experimental-strip-types --test scripts/market-index-units-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { marketIndexUnit } from '../lib/marketIndexUnit.ts';

const route = readFileSync('data-engine/app/api/routes/market.py', 'utf8');
const screener = readFileSync('app/(root)/screener/page.tsx', 'utf8');
const overview = readFileSync('components/PersonalizedOverview.tsx', 'utf8');
const actions = readFileSync('lib/actions/market.actions.ts', 'utf8');

describe('market index units guard (F152)', () => {
  it('el backend etiqueta índices como unit "index" y metales/cripto como "usd"', () => {
    assert.match(route, /\{"symbol": "\^GSPC", "name": "S&P 500", "unit": "index"\}/, '^GSPC con unit index');
    assert.match(route, /\{"symbol": "\^IXIC", "name": "Nasdaq Composite", "unit": "index"\}/, '^IXIC con unit index');
    assert.match(route, /\{"symbol": "BTC-USD", "name": "Bitcoin", "unit": "usd"\}/, 'BTC con unit usd');
  });

  it('normalización legacy sin unit: índices → index, BTC → usd, desconocido → null', () => {
    // Payload legacy (caché antigua) sin unit - el caso que reventó el bloqueo.
    assert.equal(marketIndexUnit('^GSPC', undefined), 'index', 'S&P legacy sin unit');
    assert.equal(marketIndexUnit('^IXIC', undefined), 'index', 'Nasdaq legacy sin unit');
    assert.equal(marketIndexUnit('BTC-USD', undefined), 'usd', 'BTC legacy sin unit');
    assert.equal(marketIndexUnit('ACME-XYZ', undefined), null, 'desconocido sin unit no asume USD');
  });

  it('el unit del backend se conserva cuando viene presente', () => {
    assert.equal(marketIndexUnit('^GSPC', 'index'), 'index');
    assert.equal(marketIndexUnit('GC=F', 'usd'), 'usd');
    assert.equal(marketIndexUnit('NUEVO', 'index'), 'index', 'serie nueva con unit explícita');
  });

  it('getMarketIndices normaliza en la frontera', () => {
    assert.match(actions, /marketIndexUnit\(item\.symbol, item\.unit\)/, 'normalización en la frontera');
  });

  it('los fronts solo ponen US$ cuando unit === "usd"', () => {
    assert.equal(screener.includes("formatPrice(i.price, 'USD')}"), false, 'sin formato US$ incondicional en screener');
    assert.match(screener, /i\.unit === 'usd'/, 'screener ramifica por usd explícito');
    assert.match(overview, /index\.unit === 'usd'/, 'inicio ramifica por usd explícito');
    assert.match(overview, /unit: data\.unit/, 'unit llega al estado');
  });
});

/**
 * Guarda de cotización del listado correcto (F159/F160): Finnhub free y
 * FMP /quote resuelven el ticker pelado en bolsas US. Para un emisor no-US
 * devuelven el gemelo americano - otro emisor (ALM->Almonty) o el ADR en
 * USD (ASML) - y el precio se presentaba bajo la identidad del master.
 * Backend: solo listados US cotizan con ticker pelado; Yahoo usa el sufijo
 * de la bolsa del master. Frontend: el símbolo de cotización sale del
 * master y la identidad visible la pone el master, no el proveedor.
 * Ejecución: node --experimental-strip-types --test scripts/quote-listing-match-guard.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

void test('backend: refresh de precios solo cotiza listados US con ticker pelado', () => {
    const src = readFileSync(join(here, '..', 'data-engine/app/services/market_refresh_service.py'), 'utf8');
    assert.ok(src.includes('_us_listed'), 'existe el gate de listado US');
    assert.ok(src.includes('non_us_listing'), 'razón honesta para no-US');
});

void test('backend: yahoo_symbol sale de la bolsa del master, no solo de la divisa', () => {
    const src = readFileSync(join(here, '..', 'data-engine/app/services/propicks_price_service.py'), 'utf8');
    assert.ok(src.includes('_EXCHANGE_YAHOO_SUFFIX'), 'mapa bolsa -> sufijo');
    assert.ok(src.includes('".AS"'), 'Amsterdam .AS (ASML no es .MC)');
    assert.ok(src.includes('".MC"'), 'BME .MC');
    assert.ok(src.includes('".TO"'), 'Toronto .TO');
});

void test('frontend: el símbolo sale del master y sin listado verificado no hay precio', () => {
    const mod = readFileSync(join(here, '..', 'lib/market/quote-symbol.ts'), 'utf8');
    assert.ok(mod.includes('if (!company) return null'), 'master inaccesible -> sin precio');
    assert.ok(mod.includes('EXCHANGE_YAHOO_SUFFIX'), 'mapa bolsa -> sufijo');
    const src = readFileSync(join(here, '..', 'lib/actions/market-workspace.actions.ts'), 'utf8');
    assert.ok(src.includes('quoteSymbolFor'), 'resolución de símbolo por listado');
    assert.ok(src.includes('if (!quoteSymbol)'), 'sin símbolo verificado -> unavailable');
    assert.ok(!src.includes('getProfile(normalized)'), 'profile nunca con ticker pelado');
    assert.ok(!src.includes('getStockQuote(normalized)'), 'quote nunca con ticker pelado');
    assert.ok(!src.includes('getCandles(normalized'), 'candles nunca con ticker pelado');
    assert.ok(
        src.includes('researchCompany?.name || profile?.name'),
        'la identidad visible la pone el master, el proveedor solo rellena huecos',
    );
    assert.ok(
        src.includes('researchCompany?.currency || profile?.currency'),
        'la divisa visible la pone el master',
    );
});

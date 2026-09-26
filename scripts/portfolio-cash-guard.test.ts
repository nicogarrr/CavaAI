/**
 * Guardas de la línea Caja de /portfolio (F81) y de la base de cada peso
 * (F104). La API devuelve `cash` como diccionario por moneda ya en divisa
 * base (RiskService.dashboard → calculate_portfolio_risk), NO como número:
 * el mapeo del frontend tiene que sumar los valores del diccionario.
 * Ejecución: node --experimental-strip-types --test scripts/portfolio-cash-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { sumCashByCurrency } from '../lib/portfolio-cash.ts';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const source = (relativePath: string): string => readFileSync(join(root, relativePath), 'utf8');

describe('sumCashByCurrency: respuesta real del backend { EUR: 100 }', () => {
    it('suma los valores del diccionario por moneda', () => {
        assert.equal(sumCashByCurrency({ EUR: 100 }), 100);
        assert.equal(sumCashByCurrency({ EUR: 1234.56 }), 1234.56);
        assert.equal(sumCashByCurrency({ EUR: 100, USD: 50 }), 150);
    });

    it('sin caja o caja vacía es 0: la línea Caja no se muestra', () => {
        assert.equal(sumCashByCurrency({}), 0);
        assert.equal(sumCashByCurrency(null), 0);
        assert.equal(sumCashByCurrency(undefined), 0);
        assert.equal(sumCashByCurrency({ EUR: 0 }), 0);
    });

    it('valores no finitos no contaminan la suma', () => {
        assert.equal(sumCashByCurrency({ EUR: Number.NaN }), 0);
        assert.equal(sumCashByCurrency({ EUR: Number.POSITIVE_INFINITY, USD: 25 }), 25);
    });
});

describe('contrato y mapeo del resumen', () => {
    it('el contrato declara cash como diccionario por moneda, no como número', () => {
        const actions = source('lib/actions/portfolio.actions.ts');
        const block = actions.slice(actions.indexOf('type ResearchPortfolioSummaryResponse'), actions.indexOf('};', actions.indexOf('type ResearchPortfolioSummaryResponse')));
        assert.ok(block.includes('cash: Record<string, number>'), 'cash tipado como diccionario por moneda');
        assert.ok(!block.includes('cash: number'), 'cash no puede tiparse como número: con el payload real la línea no se mostraría');
    });

    it('getPortfolioSummary deriva el importe con sumCashByCurrency', () => {
        const actions = source('lib/actions/portfolio.actions.ts');
        assert.ok(actions.includes('cash: sumCashByCurrency(backendSummary.cash)'), 'mapeo desde el diccionario del backend');
    });
});

describe('línea Caja en las tablas de posiciones', () => {
    it('móvil y escritorio muestran la línea Caja solo con caja distinta de 0', () => {
        const holdings = source('components/portfolio/PortfolioHoldings.tsx');
        assert.ok(holdings.includes("typeof cash === 'number' && cash !== 0"), 'condición explícita sobre el importe derivado');
        assert.ok(holdings.includes('Caja'), 'etiqueta de la línea');
        assert.ok(holdings.includes('border-dashed'), 'tarjeta móvil de caja diferenciada');
        assert.ok((holdings.match(/>Caja</g) ?? []).length >= 2, 'una línea Caja en móvil y otra en escritorio');
    });

    it('PortfolioTabs pasa cash y moneda base a la tabla', () => {
        const tabs = source('components/portfolio/PortfolioTabs.tsx');
        assert.ok(tabs.includes('cash={summary.cash}'), 'cash hacia PortfolioHoldings');
        assert.ok(tabs.includes('baseCurrency={summary.baseCurrency}'), 'moneda base hacia PortfolioHoldings');
    });
});

describe('donut coherente con la etiqueta "caja incluida" (F104)', () => {
    it('el donut añade un segmento Caja cuando hay caja', () => {
        const allocation = source('components/portfolio/PortfolioAllocation.tsx');
        assert.ok(allocation.includes("symbol: 'Caja'"), 'segmento Caja en los datos del donut');
        assert.ok(allocation.includes('(cashValue / totalValue) * 100'), 'peso de la caja sobre el total con caja');
        assert.ok(allocation.includes('caja incluida'), 'etiqueta que declara la base');
    });

    it('la caja no enlaza a /research/Caja ni muestra G/P inventada', () => {
        const allocation = source('components/portfolio/PortfolioAllocation.tsx');
        assert.ok(allocation.includes("item.symbol === 'Caja'"), 'la leyenda no enlaza la caja');
        const chart = source('components/portfolio/PortfolioAllocationChart.tsx');
        assert.ok(chart.includes("data.symbol === 'Caja'"), 'el tooltip distingue la caja');
        assert.ok(chart.includes('!isCash'), 'sin G/P para la caja');
    });
});

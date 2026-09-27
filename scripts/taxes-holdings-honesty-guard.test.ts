/**
 * F240: /taxes «Posiciones Fiscales» salía toda a «—» porque el backend
 * devolvía cost_basis_base/unrealized_pnl_base y la UI lista cost_basis,
 * market_value, unrealized_pnl y currency. Las claves deben coincidir y los
 * null pasan como None (NA), nunca como 0 inventado.
 * F94: al cambiar de ejercicio, el contenido del reporte debe resincronizarse
 * con el año pedido (antes el encabezado decía 2025 y el contenido era 2026).
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const backend = readFileSync('data-engine/app/services/tax_report_service.py', 'utf8');
const view = readFileSync('components/taxes/TaxesView.tsx', 'utf8');

test('el backend devuelve las claves que la UI lista', () => {
    for (const key of ['"cost_basis"', '"market_value"', '"unrealized_pnl"', '"currency"']) {
        assert.ok(backend.includes(key), `falta ${key} en build_tax_summary_rows`);
    }
    assert.match(view, /columns=\{\['ticker', 'quantity', 'cost_basis', 'market_value', 'unrealized_pnl', 'currency'\]\}/);
});

test('los null de importes pasan como None, nunca como 0 inventado', () => {
    assert.ok(!/cost_basis_base or 0/.test(backend), 'cost_basis_base or 0 fabrica un 0 desde null');
    assert.ok(!/unrealized_pnl_base or 0/.test(backend), 'unrealized_pnl_base or 0 fabrica un 0 desde null');
});

test('F94: el reporte se resincroniza al cambiar de ejercicio', () => {
    assert.match(view, /useEffect\(\(\) => \{\s*setReport\(initialReport\);\s*\}, \[year, initialReport\]\)/);
});

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

test('F94: RecordDetail se remonta al cambiar de ejercicio (key con year)', () => {
    // RecordDetail tiene useState propio sin resync: la key fuerza remount.
    assert.match(view, /key=\{recordDetailKey\(year, reportKey\)\}/);
    // y el estado local de TaxesView también se resincroniza con las props
    assert.match(view, /setReport\(initialReport\)/);
});

test('F94: la key cambia con el ejercicio aunque reportKey no cambie', async () => {
    // @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
    const { recordDetailKey } = await import('../components/taxes/record-detail-key.ts');
    assert.notEqual(recordDetailKey(2025, 0), recordDetailKey(2026, 0));
    assert.notEqual(recordDetailKey(2026, 0), recordDetailKey(2026, 1));
    assert.equal(recordDetailKey(2026, 0), '2026-0');
});

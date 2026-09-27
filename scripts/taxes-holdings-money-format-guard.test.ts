/**
 * Guard F311: «Posiciones Fiscales» nunca muestra importes crudos
 * («3589.265983»). Las tres columnas monetarias pasan por formatMoney en
 * es-ES con la divisa de la propia fila; RecordList aplica formatColumns
 * antes de caer al String(value) genérico.
 * Ejecución: node --experimental-strip-types --test scripts/taxes-holdings-money-format-guard.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
// @ts-expect-error TS5097
import { TAX_HOLDING_MONEY_COLUMNS, formatHoldingMoney } from '../lib/taxes/holding-money.ts';

void test('comportamiento: importes es-ES con divisa de la fila', () => {
    // es-ES agrupa millares a partir de 5 cifras (CLDR minimumGroupingDigits=2)
    assert.equal(formatHoldingMoney(3589.265983, 'EUR'), '3589,27 €');
    assert.equal(formatHoldingMoney(123456.789, 'EUR'), '123.456,79 €');
    assert.equal(formatHoldingMoney(-92.927388, 'EUR'), '-92,93 €');
    assert.equal(formatHoldingMoney('2159.73', 'USD'), '2159,73 US$');
    assert.equal(formatHoldingMoney(null, 'EUR'), 'N/D');
    assert.equal(formatHoldingMoney(10, 'euro'), '10,00 €', 'divisa inválida cae a EUR, nunca rompe el formato');
    assert.deepEqual([...TAX_HOLDING_MONEY_COLUMNS].sort(), ['cost_basis', 'market_value', 'unrealized_pnl']);
});

void test('RecordList aplica formatColumns antes del fallback genérico', () => {
    const views = readFileSync('components/data/RecordViews.tsx', 'utf8');
    assert.match(views, /formatColumns\?: Record<string, \(value: unknown, record: DataRecord\) => string>/);
    const cell = views.indexOf('const format = formatColumns?.[column];');
    const fallback = views.indexOf('formatRecordValue(record[column]);', cell);
    assert.ok(cell > -1 && fallback > cell, 'el formateador de columna se consulta antes del String(value)');
});

void test('TaxesView cablea las tres columnas monetarias con la divisa de la fila', () => {
    const taxes = readFileSync('components/taxes/TaxesView.tsx', 'utf8');
    assert.match(taxes, /TAX_HOLDING_MONEY_COLUMNS\.map/);
    assert.match(taxes, /formatHoldingMoney\(value, record\.currency\)/);
    assert.match(taxes, /formatColumns=\{Object\.fromEntries/);
});

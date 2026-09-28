import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const taxes = readFileSync('components/taxes/TaxesView.tsx', 'utf8');
const recordViews = readFileSync('components/data/RecordViews.tsx', 'utf8');

test('F284: /taxes etiqueta las cinco columnas fiscales visibles en español', () => {
    for (const [key, label] of Object.entries({
        ticker: 'Ticker',
        quantity: 'Cantidad',
        cost_basis: 'Base de coste',
        market_value: 'Valor de mercado',
        unrealized_pnl: 'Plusvalía latente',
    })) {
        assert.match(taxes, new RegExp(`${key}: '${label}'`), `falta etiqueta ${key}`);
    }
});

test('F284: RecordList usa las etiquetas en desktop y móvil, con fallback a la clave cruda', () => {
    // Cabecera <th> (desktop) y <dt> (cards móviles) usan el mapa; las claves
    // sin etiqueta siguen mostrándose crudas, nunca se ocultan.
    assert.equal(recordViews.match(/columnLabels\?\.\[column\] \?\? column/g)?.length, 2);
});

test('F284: la prop es opcional y tipada', () => {
    assert.match(recordViews, /columnLabels\?: Record<string, string>;/);
});

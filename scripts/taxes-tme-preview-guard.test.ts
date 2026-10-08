import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('TME manual: campo vacío, cálculo explícito y vista previa sin guardar', () => {
    const src = readFileSync('components/taxes/TmePreviewForm.tsx', 'utf8');
    assert.match(src, /useState\(''\)/);
    assert.match(src, /parseLocalizedNumber\(input\)/);
    assert.match(src, /percent === null \|\| percent < 0 \|\| percent > 100/);
    assert.match(src, /previewTaxFiling\(year, percent\)/);
    assert.match(src, /No se guarda ni sustituye tu declaración/);
    assert.match(src, /base liquidable del ahorro/);
    assert.match(src, /no el de la base general/);
});

test('Casillas por venta: 10 por página y remount al cambiar de página', () => {
    const src = readFileSync('components/taxes/FilingSections.tsx', 'utf8');
    assert.match(src, /rows\.slice\(current \* 10, \(current \+ 1\) \* 10\)/);
    assert.match(src, /RecordList key=\{current\}/);
    assert.match(src, /casillas\.available !== true/);
});

test('La exportación usa el informe mostrado, no el informe inicial viejo', () => {
    const src = readFileSync('components/taxes/TaxesView.tsx', 'utf8');
    assert.match(src, /downloadTaxSummary\(initialHoldings, report, year\)/);
    assert.match(src, /onPreview=\{\(fresh\) => setOverride\(\{ year, report: fresh \}\)\}/);
});

test('0597: sin datos nunca se pinta como 0', () => {
    const src = readFileSync('components/taxes/FilingSections.tsx', 'utf8');
    assert.match(src, /Sin datos: retenciones españolas incompletas/);
});

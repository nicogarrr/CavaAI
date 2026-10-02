/**
 * Guarda de veracidad: el WACC de la ficha solo se muestra con base
 * documentada (CalculatedMetric o InferredInput). El valor `model_policy`
 * (13 % por defecto de vista previa, sin fuente) se muestra N/D.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const SRC = readFileSync('components/research/FundamentalModelPanels.tsx', 'utf8');

void test('el panel decide el WACC con waccDisplay, no con el valor crudo', () => {
    assert.match(SRC, /function waccDisplay\(/);
    assert.match(SRC, /source_type === 'model_policy'\) return NA/);
    assert.match(SRC, /\{waccDisplay\(model\.assumptions\.wacc\)\}/);
});

void test('no queda ningun percentage() directo del WACC en el panel', () => {
    assert.doesNotMatch(SRC, /percentage\(model\.assumptions\.wacc\?\.value\)/);
});

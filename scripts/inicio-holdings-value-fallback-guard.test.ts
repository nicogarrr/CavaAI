import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const source = readFileSync(new URL('../components/PersonalizedOverview.tsx', import.meta.url), 'utf8');

test('Inicio: sin base de coste la posicion muestra valor y peso, no solo N/D', () => {
    assert.match(source, /formatMoney\(h\.value, h\.baseCurrency\)/);
    assert.match(source, /equityValue/);
});

test('Inicio: la rentabilidad solo sale con base de coste y divisa convertida', () => {
    assert.match(source, /h\.cost > 0 && !h\.fxMissing/);
});

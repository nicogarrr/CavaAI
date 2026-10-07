import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';
const source = readFileSync('components/risk/RiskDashboardView.tsx', 'utf8');
test('empty alerts do not claim safety when missing FX excludes positions', () => {
    assert.match(source, /status === 'ok'/);
    assert.match(source, /cobertura incompleta no permite descartar alertas/);
    assert.doesNotMatch(source, /ninguna posición supera los umbrales/);
});

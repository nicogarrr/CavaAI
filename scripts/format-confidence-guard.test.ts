/**
 * Veracidad: la confianza sin dato es N/D, nunca un «0%» ni un «NaN%» inventados.
 * Ejecución: node --experimental-strip-types --test scripts/format-confidence-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { formatConfidence } from '../lib/format.ts';

describe('formatConfidence', () => {
  it('formatea una confianza medida como porcentaje entero', () => {
    assert.equal(formatConfidence(0.9), '90%');
    assert.equal(formatConfidence('0.5'), '50%');
    assert.equal(formatConfidence(0), '0%');
  });

  it('sin dato o no finito es N/D, no 0% ni NaN%', () => {
    for (const value of [null, undefined, '', 'abc', Number.NaN, Number.POSITIVE_INFINITY]) {
      const out = formatConfidence(value);
      assert.ok(!out.includes('NaN') && !out.includes('Infinity'), String(value));
      assert.notEqual(out, '0%', String(value));
    }
    assert.equal(formatConfidence(null, 'Sin datos'), 'Sin datos');
  });
});

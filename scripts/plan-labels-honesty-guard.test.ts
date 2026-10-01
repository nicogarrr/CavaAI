/**
 * F368/F369: las claves nuevas del plan (cobertura parcial / aportaciones sin FX)
 * llevan etiqueta en español; sin ella saldrían como clave cruda.
 * Ejecución: node --experimental-strip-types --test scripts/plan-labels-honesty-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const view = readFileSync('components/plan/PlanView.tsx', 'utf8');

describe('etiquetas del plan (F368/F369)', () => {
    it('métricas del plan declaran las claves de cobertura de aportaciones', () => {
        for (const key of ['contributions_complete', 'contributions_missing_fx', 'actual_contributions_converted_base']) {
            assert.match(view, new RegExp(`${key}:`));
        }
    });
    it('el drift declara suggestions_blocked', () => {
        assert.match(view, /suggestions_blocked:/);
    });
});

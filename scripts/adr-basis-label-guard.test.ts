/**
 * F394 (veracidad): no se afirma una base "por acción ordinaria" sin evidencia, y
 * un ratio ADR sin valores listados tampoco se muestra como si fuera por ADR ni
 * sin etiqueta.
 * Ejecución: node --experimental-strip-types --test scripts/adr-basis-label-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { thesisScenarioDisplay, valuationScenarioDisplay } from '../lib/research/listed-share-values.ts';

const original = { bear: '8', base: '32.0375', bull: '50', expected: '31' };
const unverified = ' (base por acción no verificada)';

describe('etiquetas de base por acción (F394)', () => {
    it('tesis antigua sin evidencia: base no verificada, nunca "por acción ordinaria"', () => {
        const out = thesisScenarioDisplay(original, null);
        assert.equal(out.label, unverified);
        assert.doesNotMatch(out.label, /ordinaria/);
    });
    it('tesis con ratio pero sin listed_share_values: etiqueta base no verificada', () => {
        const out = thesisScenarioDisplay(original, { adr_ratio: 8, listed_share_values: null });
        assert.equal(out.values.base, '32.0375');
        assert.equal(out.label, unverified);
    });
    it('valoración en vivo con ratio pero sin valores listados: etiqueta base no verificada', () => {
        const out = valuationScenarioDisplay(original, { adr_ratio: 8 });
        assert.equal(out.label, unverified);
    });
    it('ratio 1 o ausente no añade aviso', () => {
        assert.equal(valuationScenarioDisplay(original, { adr_ratio: 1 }).label, '');
        assert.equal(valuationScenarioDisplay(original, null).label, '');
    });
});

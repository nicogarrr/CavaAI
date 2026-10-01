/**
 * F394: los escenarios (por acción ordinaria) no pueden mostrarse junto al
 * precio ADR sin convertir. Repro: adr:8, base 32,0375 por ordinaria -> 256,30 por ADR.
 * El cliente no multiplica: usa listed_share_values del backend; cada tesis
 * usa SU valuation_basis persistida; sin evidencia se etiqueta base no verificada.
 * Ejecución: node --experimental-strip-types --test scripts/adr-scenario-basis-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { thesisScenarioDisplay, valuationScenarioDisplay } from '../lib/research/listed-share-values.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const source = (p: string): string => readFileSync(join(root, p), 'utf8');

const original = { bear: '8', base: '32.0375', bull: '50', expected: '31' };

describe('escenarios y base por acción', () => {
    it('tesis con base persistida ADR muestra los valores convertidos del backend', () => {
        const out = thesisScenarioDisplay(original, {
            value_per_share_basis: 'ordinary_share',
            adr_ratio: 8,
            listed_share_values: { bear: 64, base: 256.3, bull: 400, expected: 248 },
        });
        assert.equal(out.values.base, 256.3);
        assert.equal(out.label, ' (por ADR, ×8)');
    });
    it('una tesis ratio 8 no se reescala con otro ratio posterior: usa solo su base', () => {
        const out = thesisScenarioDisplay(original, {
            adr_ratio: 8,
            listed_share_values: { base: 256.3 },
        });
        assert.equal(out.values.base, 256.3);
        assert.equal(out.values.bear, null);
    });
    it('tesis sin evidencia de base no escala: etiqueta base no verificada', () => {
        for (const basis of [null, undefined]) {
            const out = thesisScenarioDisplay(original, basis);
            assert.equal(out.values.base, '32.0375');
            assert.equal(out.label, ' (base por acción no verificada)');
        }
    });
    it('no ADR con base persistida (sin valores convertidos): originales sin etiqueta', () => {
        const out = thesisScenarioDisplay(original, { value_per_share_basis: 'ordinary_share', listed_share_values: null });
        assert.equal(out.values.base, '32.0375');
        assert.equal(out.label, '');
    });
    it('valoración usa los campos de su propia respuesta', () => {
        const out = valuationScenarioDisplay(original, { adr_ratio: 8, listed_share_values: { base: 256.3 } });
        assert.equal(out.values.base, 256.3);
        assert.equal(valuationScenarioDisplay(original, {}).label, '');
    });
    it('el cliente no multiplica por ratio', () => {
        const helper = source('lib/research/listed-share-values.ts');
        assert.ok(!/\*\s*ratio|ratio\s*\*/.test(helper));
        assert.match(source('components/research/ThesisMemo.tsx'), /thesisScenarioDisplay\(/);
        assert.match(source('app/(root)/research/[ticker]/page.tsx'), /valuationScenarioDisplay\(/);
    });
});

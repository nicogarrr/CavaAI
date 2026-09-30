/**
 * F394: los escenarios (por acción ordinaria) no pueden mostrarse junto al
 * precio ADR sin convertir. Repro: adr:8, base 32,0375 por ordinaria -> 256,30 por ADR.
 * Ejecución: node --experimental-strip-types --test scripts/adr-scenario-basis-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { adrRatioFromTrace, scenarioBasisLabel, toListedShareValue } from '../lib/research/listed-share-values.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const source = (p: string): string => readFileSync(join(root, p), 'utf8');

describe('conversión de escenarios a la base del precio cotizado', () => {
    it('adr:8 convierte 32,0375 por ordinaria a 256,30 por ADR', () => {
        const ratio = adrRatioFromTrace({ adr_ratio: 8 });
        assert.equal(ratio, 8);
        assert.ok(Math.abs((toListedShareValue('32.0375', ratio) as number) - 256.3) < 1e-9);
        assert.equal(scenarioBasisLabel(ratio), ' (por ADR, ×8)');
    });
    it('sin ratio no toca los valores ni añade etiqueta', () => {
        assert.equal(adrRatioFromTrace({}), null);
        assert.equal(adrRatioFromTrace({ adr_ratio: 0 }), null);
        assert.equal(toListedShareValue('32.0375', null), '32.0375');
        assert.equal(toListedShareValue(null, 8), null);
        assert.equal(scenarioBasisLabel(null), '');
    });
    it('ThesisMemo y ValuationView usan la conversión', () => {
        assert.match(source('components/research/ThesisMemo.tsx'), /toListedShareValue\(thesis\.base_value, adrRatio\)/);
        const page = source('app/(root)/research/[ticker]/page.tsx');
        assert.match(page, /toListedShareValue\(valuation\.base_value, adrRatio\)/);
        assert.match(page, /adrRatio=\{thesisAdrRatio\}/);
    });
});

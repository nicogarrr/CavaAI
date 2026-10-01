/**
 * F381: el panel de mercado mostraba el precio sin priceKind/priceAsOf; la
 * cabecera sí rotula «Cierre del …». Mismo rotulado en ambos.
 * Ejecución: node --experimental-strip-types --test scripts/market-panel-freshness-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const panel = readFileSync(join(root, 'components/research/CompanyMarketPanel.tsx'), 'utf8');

describe('panel de mercado: frescura del precio', () => {
    it('rotula cierre con fecha y fecha desconocida', () => {
        assert.match(panel, /snapshot\.quote\.priceAsOf/);
        assert.match(panel, /Cierre del/);
        assert.match(panel, /snapshot\.quote\.priceKind === 'close'/);
        assert.match(panel, /Precio de fecha desconocida/);
    });
});

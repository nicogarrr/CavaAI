/**
 * F382: el selector «Período de Rendimiento» no afectaba a ningún cálculo
 * (el servidor ignora timePeriod). Un control ficticio se retira.
 * Ejecución: node --experimental-strip-types --test scripts/propicks-period-filter-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const filters = readFileSync('components/proPicks/EnhancedProPicksFilters.tsx', 'utf8');
const content = readFileSync('components/proPicks/EnhancedProPicksContent.tsx', 'utf8');
const action = readFileSync('lib/actions/proPicks.actions.ts', 'utf8');

describe('filtro de período ProPicks (F382)', () => {
    it('el servidor sigue sin usar timePeriod, así que la UI no lo ofrece', () => {
        const body = action.slice(action.indexOf('export async function generateEnhancedProPicksWithRun'));
        assert.doesNotMatch(body.slice(0, body.indexOf('export async function generateEnhancedProPicks(')), /timePeriod/);
        assert.doesNotMatch(filters, /Período de Rendimiento/);
        assert.doesNotMatch(filters, /<SelectItem value="week">/);
    });
    it('la cabecera no muestra una etiqueta de período inexistente', () => {
        assert.doesNotMatch(content, /timePeriodLabels/);
    });
});

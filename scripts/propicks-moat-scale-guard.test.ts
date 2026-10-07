import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import { moatChecksToScore, MOAT_V2_MAX_CHECKS } from '../lib/propicks/moat-scale.ts';

describe('escala del moat V2 en el adaptador del embudo', () => {
    it('8 de 8 criterios es 100 y 4 de 8 es 50 (no 8 ni 4)', () => {
        assert.equal(MOAT_V2_MAX_CHECKS, 8);
        assert.equal(moatChecksToScore(8), 100);
        assert.equal(moatChecksToScore(4), 50);
        assert.equal(moatChecksToScore(2), 25);
        assert.equal(moatChecksToScore(0), 0);
    });

    it('acota valores fuera de rango sin inventar', () => {
        assert.equal(moatChecksToScore(9), 100);
        assert.equal(moatChecksToScore(-1), 0);
    });

    it('un pick de prod (rank 1 del run 4) supera el filtro de 70 con el moat bien escalado', () => {
        const w = { value: 0.15, growth: 0.2, profitability: 0.25, cashFlow: 0.15, momentum: 0.1, debtLiquidity: 0.15 };
        const score = (profitability: number) =>
            Math.round(100 * w.value + 100 * w.growth + profitability * w.profitability + 100 * w.cashFlow + 50 * w.momentum + 50 * w.debtLiquidity);
        assert.ok(score(8) < 70, 'con el bug (moat 8 tratado como 0-100) el pick quedaba fuera');
        assert.ok(score(moatChecksToScore(8)) >= 70, 'bien escalado entra');
    });

    it('el adaptador usa moatChecksToScore y no el moat directo', () => {
        const src = readFileSync('lib/actions/propicks-funnel.actions.ts', 'utf8');
        assert.ok(src.includes('clamp(moatChecksToScore(moat))'));
        assert.ok(!src.includes('clamp(round1(moat))'));
    });
});

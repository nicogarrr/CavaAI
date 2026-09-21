/**
 * Test ProPicks guard: sin datos futuros (as_of) y sin números inventados.
 *
 * Ejecución: node --experimental-strip-types --test scripts/propicks-guard.test.ts
 * (node:test estándar, sin dependencias nuevas ni cambios en package.json).
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import {
    validatePicks,
    validateNoFutureData,
    validateReasonsTraceable,
    validateNumbersTraceable,
    validateScoreFormula,
    PROPICKS_SCORING_WEIGHTS,
    type PickLike,
// @ts-ignore TS5097: la extensión .ts explícita la exige node --experimental-strip-types en runtime
} from '../lib/utils/propicksValidation.ts';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const readSource = (rel: string) => readFileSync(join(root, rel), 'utf8');

const NOW = new Date('2026-09-21T12:00:00.000Z');

/** Pick válido: todo número mostrado existe en facts y asOf <= ahora. */
function validPick(): PickLike {
    return {
        symbol: 'TEST',
        asOf: '2026-09-20T18:00:00.000Z',
        facts: {
            price: 100,
            targetMean: 120,
            upside: 20,
            return12M: 25,
            vsSP500: 8,
            cat_value: 80,
            cat_growth: 70,
            cat_profitability: 90,
            cat_cashFlow: 60,
            cat_momentum: 75,
            cat_debtLiquidity: 65,
        },
        confidenceReasons: [
            { metric: 'upside', value: 20, text: 'Potencial alcista del 20% (objetivo $120 vs $100)' },
            { metric: 'cat_profitability', value: 90, text: 'Rentabilidad 90/100 (+12 vs sector)' },
        ],
        currentPrice: 100,
        targetPrice: 120,
        upsidePotential: 20,
        // 80*.15+70*.20+90*.25+60*.15+75*.10+65*.15 = 74.75 → 75
        score: 75,
        categoryScores: {
            value: 80,
            growth: 70,
            profitability: 90,
            cashFlow: 60,
            momentum: 75,
            debtLiquidity: 65,
        },
    };
}

describe('propicks-guard', () => {
    it('pick válido pasa las 4 reglas', () => {
        assert.deepEqual(validatePicks([validPick()], NOW), []);
    });

    it('R1: rechaza asOf futuro (datos futuros)', () => {
        const pick = validPick();
        pick.asOf = '2026-09-22T12:00:00.000Z';
        const issues = validateNoFutureData(pick, NOW);
        assert.equal(issues.length, 1);
        assert.equal(issues[0].rule, 'R1-as_of');
    });

    it('R1: rechaza pick sin asOf', () => {
        const pick = validPick();
        pick.asOf = '';
        assert.ok(validateNoFutureData(pick, NOW).length > 0);
    });

    it('R2: rechaza motivo con métrica ausente en facts (número inventado)', () => {
        const pick = validPick();
        pick.confidenceReasons = [
            ...pick.confidenceReasons,
            { metric: 'perMagico', value: 5, text: 'PER mágico de 5 (inventado)' },
        ];
        const issues = validateReasonsTraceable(pick);
        assert.ok(issues.some((i) => i.message.includes('perMagico')));
    });

    it('R2: rechaza motivo cuyo valor no coincide con facts', () => {
        const pick = validPick();
        pick.confidenceReasons = [
            { metric: 'upside', value: 99, text: 'Potencial alcista del 99% (falso)' },
            pick.confidenceReasons[1],
        ];
        assert.ok(validateReasonsTraceable(pick).length > 0);
    });

    it('R2: exige al menos 2 motivos trazables', () => {
        const pick = validPick();
        pick.confidenceReasons = [pick.confidenceReasons[0]];
        assert.ok(validateReasonsTraceable(pick).length > 0);
    });

    it('R3: rechaza upside incoherente con precio y objetivo', () => {
        const pick = validPick();
        pick.upsidePotential = 50; // real: (120-100)/100*100 = 20
        const issues = validateNumbersTraceable(pick);
        assert.ok(issues.some((i) => i.rule === 'R3-numeros'));
    });

    it('R3: rechaza currentPrice que no viene de facts/quotes', () => {
        const pick = validPick();
        pick.currentPrice = 10;
        assert.ok(validateNumbersTraceable(pick).length > 0);
    });

    it('R4: rechaza score que no reproduce la fórmula documentada', () => {
        const pick = validPick();
        pick.score = 10;
        const issues = validateScoreFormula(pick);
        assert.equal(issues.length, 1);
        assert.equal(issues[0].rule, 'R4-score');
    });

    it('pesos canónicos suman 1.0', () => {
        const total = Object.values(PROPICKS_SCORING_WEIGHTS).reduce((a, b) => a + b, 0);
        assert.ok(Math.abs(total - 1) < 1e-9, `suma = ${total}`);
    });

    it('SCORING_WEIGHTS del código coincide con los pesos canónicos', () => {
        const src = readSource('lib/utils/advancedStockScoring.ts');
        for (const [key, weight] of Object.entries(PROPICKS_SCORING_WEIGHTS)) {
            assert.ok(
                src.includes(`${key}: ${weight}`),
                `SCORING_WEIGHTS debe declarar ${key}: ${weight}`,
            );
        }
        assert.ok(src.includes('overallScore = round(') || src.includes('FÓRMULA DE SCORING'));
    });

    it('el action expone asOf, facts y confianza trazable', () => {
        const src = readSource('lib/actions/proPicks.actions.ts');
        for (const token of ['asOf', 'confidenceReasons', 'facts', 'confidenceLevel', 'buildConfidence']) {
            assert.ok(src.includes(token), `proPicks.actions.ts debe contener ${token}`);
        }
    });

    it('UI en español con reintento', () => {
        const content = readSource('components/proPicks/EnhancedProPicksContent.tsx');
        const tabs = readSource('components/proPicks/ProPicksTabs.tsx');
        const section = readSource('components/proPicks/ProPicksSection.tsx');
        assert.ok(content.includes('Reintentar'));
        assert.ok(tabs.includes('Reintentar'));
        assert.ok(section.includes('Reintentar'));
        assert.ok(!content.includes('Regenerar Picks') || content.includes('Reintentar'));
    });
});

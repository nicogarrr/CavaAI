/**
 * Guarda F145: el máximo drawdown de ProPicks usa la misma convención de
 * signo que el backend (_drawdown) y /portfolio/intelligence: valor <= 0,
 * la pérdida se muestra con signo menos. Antes, /propicks mostraba la
 * magnitud en positivo («8,12 %») mientras intelligence mostraba «-17,8 %»
 * para el mismo concepto.
 *
 * Ejecución: node --experimental-strip-types --test scripts/propicks-drawdown-sign-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const readSource = (rel: string) => readFileSync(join(root, rel), 'utf8');

const ACTION = 'lib/actions/propicks-backtest.actions.ts';
const WALK_FORWARD = 'components/proPicks/WalkForwardResults.tsx';
const FACTSHEET = 'components/proPicks/StrategyFactsheet.tsx';

describe('propicks drawdown sign guard (F145)', () => {
    it('la acción emite maxDD firmado (<= 0), no la magnitud en positivo', () => {
        const src = readSource(ACTION);
        assert.ok(
            src.includes('maxDD: wfPct2(-maxDD)'),
            'propicks-backtest.actions.ts debe emitir maxDD con signo negativo (convención backend)',
        );
        assert.ok(
            !src.includes('maxDD: wfPct2(maxDD)'),
            'maxDD en positivo rompe la coherencia de signo con /portfolio/intelligence',
        );
    });

    it('las vistas no niegan ni toman valor absoluto: muestran el signo tal cual', () => {
        for (const rel of [WALK_FORWARD, FACTSHEET]) {
            const src = readSource(rel);
            assert.ok(!/[-]result\.maxDD|-m\.maxDD|-wf\.maxDD/.test(src), `${rel} no debe re-negar maxDD`);
            assert.ok(!/Math\.abs\([^)]*maxDD/.test(src), `${rel} no debe aplicar Math.abs a maxDD`);
        }
    });

    it('la documentación del tipo declara la convención de signo', () => {
        const src = readSource(ACTION);
        const docLine = src.split('\n').find((line) => line.includes('Máximo drawdown'));
        assert.ok(docLine, 'falta la doc de maxDD');
        assert.match(docLine, /con signo|<= 0/, 'la doc de maxDD debe declarar la convención firmada');
    });
});

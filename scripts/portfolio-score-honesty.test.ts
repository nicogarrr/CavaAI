/**
 * Guardas de honestidad de los factores de cartera.
 *
 * Un "0" de puntuacion es una medicion; la ausencia de la metrica que la
 * alimenta no lo es. El action devolvia cinco ceros cuando no habia tearsheet,
 * cuando no habia posiciones y cuando el backend fallaba, y la UI los pintaba
 * como "0,00": un fallo de red se veia como una cartera con calidad 0.
 *
 * Ejecucion: node --experimental-strip-types --test scripts/portfolio-score-honesty.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const source = (relativePath: string): string => readFileSync(join(root, relativePath), 'utf8');

describe('factores de cartera: ausente no es cero', () => {
  it('el action declara las puntuaciones como number | null', () => {
    const actions = source('lib/actions/portfolio.actions.ts');
    const declared = /export type PortfolioScores = \{[\s\S]*?\n\};/.exec(actions);
    assert.ok(declared, 'debe existir el tipo PortfolioScores');
    for (const key of ['quality', 'growth', 'value', 'dividend', 'cagr3y']) {
      assert.ok(
        new RegExp(`${key}: number \\| null;`).test(declared[0]),
        `PortfolioScores debe declarar ${key}: number | null`,
      );
    }
  });

  it('una metrica ausente produce null, no 0', () => {
    const actions = source('lib/actions/portfolio.actions.ts');
    for (const pattern of [
      'sharpe == null ? null',
      'cumulative == null ? null',
      'maxDD == null ? null',
    ]) {
      assert.ok(actions.includes(pattern), `falta el patron ausente->null: ${pattern}`);
    }
    assert.ok(
      !actions.includes('sharpe == null ? 0'),
      'un Sharpe ausente no puede volverse 0',
    );
  });

  it('un fallo del backend devuelve factores ausentes, no una cartera de ceros', () => {
    const actions = source('lib/actions/portfolio.actions.ts');
    const catchBlock = actions.slice(actions.lastIndexOf("console.error('Error getting portfolio scores"));
    assert.ok(
      catchBlock.includes('NO_PORTFOLIO_SCORES'),
      'el catch de getPortfolioScores debe devolver NO_PORTFOLIO_SCORES',
    );
    const empty = /const NO_PORTFOLIO_SCORES = \{[\s\S]*?\} as const/.exec(actions);
    assert.ok(empty, 'debe existir NO_PORTFOLIO_SCORES');
    for (const key of ['quality', 'growth', 'value', 'dividend', 'cagr3y']) {
      assert.ok(
        new RegExp(`${key}: null`).test(empty[0]),
        `NO_PORTFOLIO_SCORES debe dejar ${key} en null`,
      );
    }
    assert.ok(
      !/NO_PORTFOLIO_SCORES = \{[^}]*quality: 0/.test(actions),
      'NO_PORTFOLIO_SCORES no puede llevar ceros',
    );
  });

  it('la pagina no fabrica ceros cuando los factores no llegan', () => {
    const page = source('app/(root)/portfolio/page.tsx');
    assert.ok(
      !page.includes('quality: 0, growth: 0, value: 0, dividend: 0, cagr3y: 0'),
      'el fallback de getPortfolioScores en page.tsx no puede ser una cartera de ceros',
    );
    assert.ok(
      page.includes('quality: null, growth: null, value: null, dividend: null, cagr3y: null'),
      'el fallback debe marcar los cinco factores como ausentes',
    );
  });

  it('la UI dice "sin datos" en vez de renderizar 0,00', () => {
    const component = source('components/portfolio/PortfolioScores.tsx');
    assert.ok(component.includes('sin datos'), 'la tarjeta debe rotular los factores sin datos');
    assert.ok(
      component.includes('item.value == null'),
      'la tarjeta debe distinguir null de un 0 real',
    );
    assert.ok(
      !/value: number;/.test(component),
      'las props de la tarjeta no pueden exigir number: admiten null',
    );
  });
});

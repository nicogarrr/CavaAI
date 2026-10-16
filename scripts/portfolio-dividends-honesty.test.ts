/**
 * Guardas de honestidad de la proyección de dividendos (idea 5, listado 0-31).
 *
 * La pestaña pinta cifras del endpoint determinista
 * /api/portfolio/dividends/projection. Las reglas que no pueden regresar:
 *
 *  1. Ausencia no es cero: los null del backend (sin fx, sin retención
 *     verificada, escenario fiscal no disponible) se pintan N/D, nunca 0,00.
 *  2. La etiqueta INFERIDO viaja del payload a la pantalla: es una réplica
 *     mecánica de lo declarado, no un compromiso de la empresa.
 *  3. Las posiciones excluidas se nombran (subconjunto cubierto), no se
 *     agregan en silencio.
 *  4. El método y las condiciones del escenario fiscal son accesibles desde
 *     la propia vista.
 *
 * Ejecución: node --experimental-strip-types --test scripts/portfolio-dividends-honesty.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const source = (relativePath: string): string => readFileSync(join(root, relativePath), 'utf8');

describe('proyección de dividendos: ausente no es cero', () => {
  it('la vista usa formatMoney con su fallback N/D, sin ?? 0 en importes', () => {
    const view = source('components/portfolio/PortfolioDividends.tsx');
    assert.ok(view.includes("from '@/lib/format'"), 'debe formatear con lib/format');
    assert.ok(!/\?\?\s*0(?![\d.])/.test(view), 'un importe ausente no puede volverse 0');
    assert.ok(view.includes("'N/D'"), 'los importes sin cobertura se pintan N/D');
  });

  it('el tipo declara los campos fiscales como number | null', () => {
    const actions = source('lib/actions/portfolio.actions.ts');
    const declared = /export type DividendProjectionFiscalYear = \{[\s\S]*?\n\};/.exec(actions);
    assert.ok(declared, 'debe existir DividendProjectionFiscalYear');
    for (const key of ['gross_base', 'irpf_scenario', 'net_scenario', 'cuota_pendiente_estimada']) {
      assert.ok(
        new RegExp(`${key}: number \\| null;`).test(declared[0]),
        `DividendProjectionFiscalYear debe declarar ${key}: number | null`,
      );
    }
  });

  it('la etiqueta del backend (INFERIDO) se pinta tal cual', () => {
    const view = source('components/portfolio/PortfolioDividends.tsx');
    assert.ok(view.includes('projection.label'), 'la etiqueta de veracidad viene del payload');
    const actions = source('lib/actions/portfolio.actions.ts');
    assert.ok(actions.includes('label: string;'), 'el tipo conserva la etiqueta del backend');
  });

  it('las posiciones excluidas se nombran, no se agregan en silencio', () => {
    const view = source('components/portfolio/PortfolioDividends.tsx');
    assert.ok(view.includes('excluded_tickers'), 'las excluidas del mes/año se listan');
    assert.ok(view.includes('sin datos, no cero'), 'la exclusión se explica como ausencia, no como cero');
  });

  it('el método y las condiciones fiscales son accesibles desde la vista', () => {
    const view = source('components/portfolio/PortfolioDividends.tsx');
    assert.ok(view.includes('projection.method'), 'el método del cálculo es visible');
    assert.ok(view.includes('projection.fiscal_conditions'), 'las condiciones del escenario son visibles');
    assert.ok(view.includes('projection.sources'), 'las fuentes son enlazables');
  });
});

/**
 * Guardas de la capa de UI: separadores es-ES, tabs móviles y etiquetas visibles.
 * Ejecución: node --experimental-strip-types --test scripts/ui-format-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { formatMoney, formatNumber, formatPercent } from '../lib/format.ts';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const source = (relativePath: string): string => readFileSync(join(root, relativePath), 'utf8');

describe('formato numérico es-ES', () => {
  it('usa coma decimal en números, porcentajes e importes', () => {
    assert.equal(formatNumber(-0.8), '-0,8');
    assert.equal(formatPercent(-0.008, { digits: 2 }), '-0,80\u00a0%');
    assert.equal(formatMoney(1234.5), '1234,50\u00a0US$');
  });
});

describe('guardas de UI', () => {
  it('la lista de ProPicks usa scroll horizontal real en móvil', () => {
    const tabs = source('components/proPicks/ProPicksTabs.tsx');
    for (const token of ['flex h-auto w-max', 'min-w-full', 'overflow-x-auto', 'snap-x', 'pb-2', 'sm:inline-flex']) {
      assert.ok(tabs.includes(token), `ProPicksTabs debe contener ${token}`);
    }
    const triggers = tabs.slice(tabs.indexOf('<TabsList'), tabs.indexOf('</TabsList>'));
    assert.equal((triggers.match(/min-w-fit/g) ?? []).length, 4);
    assert.equal((triggers.match(/whitespace-nowrap/g) ?? []).length, 4);
    // Con viewport de 390 px, los cuatro triggers conservan su ancho natural;
    // el contenedor, no cada tab, es quien desborda horizontalmente.
    for (const token of ['w-max', 'min-w-full', 'overflow-x-auto']) assert.ok(tabs.includes(token), `ProPicksTabs debe contener ${token}`);
  });

  it('los formateadores UI de los módulos asignados no usan toFixed', () => {
    for (const file of [
      'lib/actions/correlation.actions.ts',
      'lib/actions/screener.actions.ts',
      'lib/utils/advancedStockScoring.ts',
    ]) {
      assert.equal(source(file).includes('.toFixed('), false, `${file} debe delegar en lib/format.ts`);
    }
  });

  it('los valores Unknown visibles se traducen sin cambiar enums de API', () => {
    for (const file of [
      'lib/actions/correlation.actions.ts',
      'lib/actions/finnhub.actions.ts',
      'lib/actions/screener.actions.ts',
      'lib/utils/advancedStockScoring.ts',
    ]) {
      assert.equal(source(file).includes("'Unknown'"), false, `${file} debe mostrar Desconocido`);
    }
    const proPicks = source('lib/actions/proPicks.actions.ts');
    assert.ok(proPicks.includes("profile.finnhubIndustry ?? profile.industry ?? 'Desconocido'"));
    assert.ok(proPicks.includes("profile.finnhubIndustry ?? profile.industry ?? 'Desconocido'"));
  });

  it('mantiene las etiquetas de estado en español sin cambiar enums de API', () => {
    assert.ok(source('app/(root)/research/workflows/page.tsx').includes("partial: 'Parcial'"));
    assert.ok(source('app/(root)/research/[ticker]/management-credibility/page.tsx').includes("partial: 'Parcial'"));
  });

  it('traduce el typo del monitor insider y no lo replica en la UI', () => {
    const insider = source('app/(root)/insider/page.tsx');
    assert.ok(insider.includes('monitor automático'));
    assert.equal(insider.includes('monitor automatico'), false);
  });
});

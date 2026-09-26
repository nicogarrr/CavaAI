/**
 * F215: un fallo del proveedor de búsqueda NO es "sin resultados". La acción
 * debe exponer el estado y la UI debe distinguir error de lista vacía.
 * Ejecución: node --experimental-strip-types --test scripts/search-status-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { createLatestRequestGate } from '../lib/latest-request.ts';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const source = (relativePath: string): string => readFileSync(join(root, relativePath), 'utf8');

describe('F215: búsqueda con estado explícito', () => {
  it('la acción expone searchStocksWithStatus con discriminación ok/error', () => {
    const actions = source('lib/actions/finnhub.actions.ts');
    assert.ok(actions.includes("searchStocksWithStatus"), 'debe existir la variante con estado');
    assert.ok(actions.includes("status: 'error'"), 'el fallo del proveedor debe ser visible');
    // la implementación interna lanza; no traga el error antes de la variante con estado
    assert.ok(actions.includes('searchStocksOrThrow'), 'la lógica interna debe poder lanzar');
  });

  it('el buscador global no pinta "sin resultados" cuando el proveedor falla', () => {
    const cmd = source('components/SearchCommand.tsx');
    assert.ok(cmd.includes('searchStocksWithStatus'), 'SearchCommand debe usar la variante con estado');
    assert.ok(
      cmd.includes("result.status === 'error'"),
      'el error del proveedor debe activar el estado de error, no la lista vacía',
    );
  });

  it('la ruta sin query delega en getPopularStocks (0/10 es error, no lista vacía)', () => {
    const actions = source('lib/actions/finnhub.actions.ts');
    const noQuery = actions.slice(actions.indexOf('if (!trimmed)'), actions.indexOf('} else {', actions.indexOf('if (!trimmed)')));
    assert.ok(noQuery.includes('getPopularStocks()'), 'sin query debe delegar en getPopularStocks');
    assert.ok(noQuery.includes("popular.status === 'error'"), '0/10 perfiles debe propagarse como error');
  });

  it('gate: una respuesta tardía de una query vieja no pisa la nueva (race)', () => {
    const gate = createLatestRequestGate();
    const vieja = gate.begin();
    const nueva = gate.begin();
    assert.equal(gate.isLatest(vieja), false, 'la query vieja queda invalidada');
    assert.equal(gate.isLatest(nueva), true, 'la nueva es la única aplicable');
    const masNueva = gate.begin();
    assert.equal(gate.isLatest(nueva), false);
    assert.equal(gate.isLatest(masNueva), true);
  });

  it('el alta de transacciones invalida respuestas tardías y limpia el error al borrar', () => {
    const add = source('components/portfolio/AddTransactionButton.tsx');
    assert.ok(add.includes('searchGateRef.current.begin()'), 'cada búsqueda pide ticket');
    assert.ok(
      (add.match(/isLatest\(ticket\)/g) ?? []).length >= 2,
      'tanto la vía ok como la de error comprueban el ticket antes de pintar',
    );
    // al borrar la query se limpia el error en las dos ramas de salida
    const emptyBranch = add.slice(add.indexOf('if (query.length < 1)'), add.indexOf('setSearchLoading(true);'));
    assert.ok(emptyBranch.includes('setSearchError(false)'), 'borrar la query limpia el error');
  });

  it('el alta de transacciones tampoco confunde error con "sin resultados"', () => {
    const add = source('components/portfolio/AddTransactionButton.tsx');
    assert.ok(add.includes('searchStocksWithStatus'), 'AddTransactionButton debe usar la variante con estado');
    assert.ok(add.includes('searchError'), 'debe tener estado de error visible');
  });
});

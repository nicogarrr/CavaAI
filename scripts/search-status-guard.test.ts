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

  it('el alta de transacciones tampoco confunde error con "sin resultados"', () => {
    const add = source('components/portfolio/AddTransactionButton.tsx');
    assert.ok(add.includes('searchStocksWithStatus'), 'AddTransactionButton debe usar la variante con estado');
    assert.ok(add.includes('searchError'), 'debe tener estado de error visible');
  });
});

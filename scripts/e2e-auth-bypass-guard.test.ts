/**
 * Guarda del bypass de auth E2E (auditoría 2026-09-25, P1):
 * E2E_AUTH_BYPASS=1 solo abre la sesión sintética cuando APP_ENV==='test'.
 * Un E2E_AUTH_SECRET no vacío por sí solo NO debe bastar.
 * Ejecución: node --experimental-strip-types --test scripts/e2e-auth-bypass-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, '..', 'lib/auth/require-user.ts'), 'utf8');

describe('bypass de auth E2E (require-user.ts)', () => {
  it('exige APP_ENV=test estricto además de E2E_AUTH_BYPASS=1', () => {
    assert.match(source, /process\.env\.APP_ENV === 'test'/);
    assert.match(source, /process\.env\.E2E_AUTH_BYPASS === '1'/);
    assert.match(source, /process\.env\.NODE_ENV !== 'production'/);
  });

  it('un E2E_AUTH_SECRET no vacío NO habilita el bypass', () => {
    assert.doesNotMatch(source, /E2E_AUTH_SECRET != null/);
    assert.doesNotMatch(source, /E2E_AUTH_SECRET !== ''/);
  });
});

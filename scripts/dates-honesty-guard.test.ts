/**
 * Veracidad de fechas: el año fiscal es el del usuario (Europe/Madrid), no el
 * del runner, y el sitemap no declara una frescura que no tiene.
 * Ejecución: node --experimental-strip-types --test scripts/dates-honesty-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
// Solo código: los comentarios explican el porqué y citan la expresión antigua.
const read = (...parts: string[]) =>
  readFileSync(join(root, ...parts), 'utf8')
    .split('\n')
    .filter((line) => !line.trim().startsWith('//'))
    .join('\n');

describe('fechas honestas', () => {
  it('taxes mide el año fiscal en la zona del usuario, no con getFullYear() del servidor', () => {
    const page = read('app', '(root)', 'taxes', 'page.tsx');
    assert.doesNotMatch(page, /new Date\(\)\.getFullYear\(\)/);
    assert.match(page, /timeZone:\s*USER_TZ/);
  });

  it('el sitemap no inventa lastModified: new Date() en rutas estáticas', () => {
    const sitemap = read('app', 'sitemap.ts');
    assert.doesNotMatch(sitemap, /lastModified/);
  });
});

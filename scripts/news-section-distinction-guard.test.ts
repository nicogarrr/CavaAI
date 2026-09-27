/**
 * Guarda F149: «Noticias destacadas» de /inicio mezcla titulares vinculados a
 * símbolos del usuario con mercado general. Cada tarjeta debe distinguirlo
 * (insignia de ticker o «Mercado general») y el módulo debe explicar el
 * criterio - 4/6 titulares generales sin marcar sugerían vínculo con la
 * cartera que no existe.
 *
 * Ejecución: node --experimental-strip-types --test scripts/news-section-distinction-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const src = readFileSync(join(root, 'components/NewsSection.tsx'), 'utf8');

describe('news section distinction guard (F149)', () => {
    it('los titulares sin vínculo se etiquetan «Mercado general»', () => {
        assert.ok(src.includes('Mercado general'), 'falta la insignia para noticias sin ticker vinculado');
        assert.ok(src.includes('article.related ?'), 'la insignia de ticker debe ser condicional al vínculo real');
    });

    it('el módulo explica el criterio de selección', () => {
        assert.ok(
            src.includes('sin vínculo con tu cartera'),
            'falta la explicación del criterio (símbolos propios vs mercado general)',
        );
    });
});

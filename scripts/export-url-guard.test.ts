/**
 * Guarda SSRF de la exportación del journal: la server action debe fijar el
 * destino al backend configurado y no dejar que valores del cliente compongan
 * la URL del fetch (CodeQL js/request-forgery).
 * Ejecución: node --experimental-strip-types --test scripts/export-url-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, '..', 'lib', 'actions', 'export.actions.ts'), 'utf8');

describe('exportJournal fija el destino de la petición', () => {
    it('la ruta sale de un mapa de constantes: year solo actua de clave', () => {
        assert.match(src, /const EXPORT_PATHS/);
        assert.match(src, /const exportPath = EXPORT_PATHS\[year\]/);
        assert.match(src, /new URL\(exportPath, BACKEND_URL\)/);
        assert.doesNotMatch(src, /new URL\(`\/api\/export\/\$\{year\}`/);
    });

    it('no interpola valores en la URL del fetch por template literal', () => {
        assert.doesNotMatch(src, /fetch\(\s*`/);
    });

    it('fija el origen al del backend configurado antes de llamar', () => {
        assert.match(src, /exportUrl\.origin !== new URL\(BACKEND_URL\)\.origin/);
    });

    it('valida format en runtime y lo mapea a un literal constante', () => {
        assert.match(src, /format !== 'csv' && format !== 'json'/);
        assert.match(src, /format === 'csv' \? 'csv' : 'json'/);
        assert.match(src, /searchParams\.set\('format', safeFormat\)/);
    });

    it('mantiene year acotado a un entero razonable', () => {
        assert.match(src, /Number\.isInteger\(year\)/);
        assert.match(src, /year < 2000 \|\| year > 2100/);
    });

    it('el error publico es generico y el detalle crudo solo va al log', () => {
        assert.doesNotMatch(src, /detail\.slice\(0, 300\)/);
        assert.match(src, /console\.error\(/);
        assert.match(src, /`Exportación falló \(\$\{response\.status\}\)`/);
    });
});

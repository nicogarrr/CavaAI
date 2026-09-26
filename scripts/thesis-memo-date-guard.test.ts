/**
 * Test del guard de fecha inválida en la etiqueta "generada el ..." de la tesis.
 *
 * Ejecución: node --experimental-strip-types --test scripts/thesis-memo-date-guard.test.ts
 * (node:test estándar, sin dependencias nuevas ni cambios en package.json).
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
// @ts-expect-error TS5097: la extensión .ts explícita la exige node --experimental-strip-types en runtime
import { formatGeneratedDate, NA } from '../lib/format.ts';

const here = dirname(fileURLToPath(import.meta.url));
const componentSrc = readFileSync(
    join(here, '..', 'components', 'research', 'ThesisMemo.tsx'),
    'utf8',
);

describe('formatGeneratedDate', () => {
    it('fecha inválida (string no parseable) devuelve null, nunca el placeholder', () => {
        assert.equal(formatGeneratedDate('no-es-una-fecha'), null);
    });

    it('Date inválida (NaN) devuelve null', () => {
        assert.equal(formatGeneratedDate(new Date(Number.NaN)), null);
    });

    it('fecha ausente (null/undefined) devuelve null', () => {
        assert.equal(formatGeneratedDate(null), null);
        assert.equal(formatGeneratedDate(undefined), null);
    });

    it('fecha válida se formatea y no es el placeholder', () => {
        const label = formatGeneratedDate('2026-01-15T12:00:00Z');
        assert.ok(label !== null && label.length > 0);
        assert.notEqual(label, NA);
        assert.match(label, /2026/);
    });

    it('sin el guard, una fecha inválida caería en el fallback N/D (riesgo que se evita)', () => {
        // Documenta el riesgo: el fallback por defecto de formatUserDate
        // pintaría "generada el N/D" para un timestamp roto.
        const raw = new Date('no-es-una-fecha');
        assert.ok(Number.isNaN(raw.getTime()));
    });
});

describe('ThesisMemo mantiene el guard explícito', () => {
    it('la etiqueta generada pasa por formatGeneratedDate (con guard), no por formatUserDate a pelo', () => {
        assert.match(componentSrc, /formatGeneratedDate\(thesis\.created_at\)/);
        // Ninguna llamada directa a formatUserDate para la etiqueta generada.
        assert.doesNotMatch(componentSrc, /formatUserDate\(generatedAt/);
    });
});

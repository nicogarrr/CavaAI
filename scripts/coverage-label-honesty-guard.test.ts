/**
 * Guarda F147: ninguna etiqueta de «cobertura» puede sugerir completitud
 * cuando la tesis/modelo está bloqueado por entradas faltantes.
 * - Auditorías: el score es % de afirmaciones MATERIALES con fuente citada
 *   (source_auditor.py), no completitud de valoración: se etiqueta como tal.
 * - Modelo: la cobertura cuenta valores presentes con source_fact_ids; con
 *   missing_inputs el porcentaje se omite para no dar seguridad errónea.
 *
 * Ejecución: node --experimental-strip-types --test scripts/coverage-label-honesty-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const readSource = (rel: string) => readFileSync(join(root, rel), 'utf8');

describe('coverage label honesty guard (F147)', () => {
    it('las auditorías etiquetan el score con su fórmula real (respaldo menos penalización)', () => {
        // source_coverage_score = % afirmaciones con fuente - 5 por weak claim:
        // «N/100 con fuente» sería falso cuando hay débiles.
        const label = 'puntuación de respaldo de afirmaciones';
        const penalty = '(penaliza baja confianza)';
        const sources = readSource('app/(root)/research/sources/page.tsx');
        assert.ok(sources.includes(label), 'sources debe nombrar la puntuación de respaldo');
        assert.ok(sources.includes(penalty), 'sources debe declarar la penalización por baja confianza');
        assert.ok(!sources.includes('>cobertura {formatNumber'), 'etiqueta «cobertura» sin alcance prohibida');
        assert.ok(!sources.includes('afirmaciones con fuente'), '«con fuente» es falso: el score descuenta débiles');
        const research = readSource('app/(root)/research/[ticker]/page.tsx');
        assert.ok(research.includes(label), 'la ficha debe nombrar la puntuación de respaldo');
        assert.ok(research.includes(penalty), 'la ficha debe declarar la penalización');
        assert.ok(!research.includes('>cobertura {audit.source_coverage_score}'), 'etiqueta «cobertura» sin alcance prohibida');
    });

    it('el modelo usa publishable como puerta y nunca oculta la causa', () => {
        const src = readSource('components/research/FundamentalModelPanels.tsx');
        assert.ok(
            src.includes("model.publishable ? '' : ' · modelo no publicable'"),
            'la puerta de estado debe ser model.publishable (cubre missing_inputs, bloqueos y cobertura <60)',
        );
        assert.ok(
            !src.includes('model.missing_inputs.length === 0'),
            'missing_inputs solo no basta: publishable=false también por cobertura <60 con inputs completos',
        );
        assert.ok(
            src.includes('valores con fuente'),
            'el porcentaje siempre lleva su alcance: valores presentes con fuente',
        );
        assert.ok(
            !src.includes('· cobertura {formatNumber(model.source_coverage.coverage_percent'),
            '«cobertura N %» sin alcance junto a INSUFFICIENT_DATA da seguridad errónea',
        );
    });
});

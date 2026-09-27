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
    it('las auditorías etiquetan el score como afirmaciones con fuente, con unidad /100', () => {
        const sources = readSource('app/(root)/research/sources/page.tsx');
        assert.ok(
            sources.includes('afirmaciones con fuente {formatNumber(audit.source_coverage_score'),
            'sources debe etiquetar el alcance del score',
        );
        assert.ok(!sources.includes('>cobertura {formatNumber'), 'etiqueta «cobertura» sin alcance prohibida');
        const research = readSource('app/(root)/research/[ticker]/page.tsx');
        assert.ok(
            research.includes('afirmaciones con fuente {audit.source_coverage_score}/100'),
            'la ficha debe etiquetar el alcance del score',
        );
        assert.ok(!research.includes('>cobertura {audit.source_coverage_score}'), 'etiqueta «cobertura» sin alcance prohibida');
    });

    it('el modelo omite el porcentaje de cobertura cuando no es publicable', () => {
        const src = readSource('components/research/FundamentalModelPanels.tsx');
        assert.ok(
            src.includes("model.missing_inputs.length === 0"),
            'el porcentaje solo se muestra sin entradas faltantes',
        );
        assert.ok(
            src.includes("' · modelo no publicable'"),
            'con entradas faltantes la cabecera declara no publicable en vez de un 100 % tranquilizador',
        );
        assert.ok(
            !src.includes('· cobertura {formatNumber(model.source_coverage.coverage_percent'),
            '«cobertura N %» sin alcance junto a INSUFFICIENT_DATA da seguridad errónea',
        );
        assert.ok(
            src.includes('valores con fuente'),
            'cuando se muestra, la etiqueta dice qué cubre: valores presentes con fuente',
        );
    });
});

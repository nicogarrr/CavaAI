/**
 * Guarda F178: la metodología de ProPicks no puede prometer lo que v1 no
 * tiene. Antes /metodologia afirmaba que la selección combina valor y
 * momentum con rebalanceo mensual y backtest por estrategia publicado,
 * mientras el embudo v1 de la misma página declara que valoración y
 * momentum aún NO entran (necesitan series de precios no persistidas).
 * La tarjeta «Sobre ProPicks IA» de /propicks listaba «✓ Evaluación de
 * momentum» y «✓ Comparación con sector», ambas falsas en v1 (el ranking
 * es por percentiles del universo, sin momentum).
 *
 * Ejecución: node --experimental-strip-types --test scripts/propicks-methodology-honesty-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const readSource = (rel: string) => readFileSync(join(root, rel), 'utf8');

describe('propicks methodology honesty guard (F178)', () => {
    it('la metodología no promete valor/momentum ni backtest por estrategia como presente', () => {
        const page = readSource('app/(public)/metodologia/page.tsx');
        assert.ok(!page.includes('están publicadas con sus métricas'), 'las estrategias no se declaran publicadas');
        assert.ok(!page.includes('se rebalancea el día 1 de cada'), 'sin rebalanceo mensual prometido');
        assert.ok(
            page.includes('La valoración\n          (FCF yield / earnings yield) y el momentum aún no entran') ||
                page.includes('valoración\n          (FCF yield / earnings yield) y el momentum aún no entran'),
            'el resumen declara que valoración y momentum aún no entran en v1',
        );
        assert.ok(
            page.includes('El backtest por estrategia se publicará cuando existan fundamentales point-in-time'),
            'el backtest por estrategia se declara pendiente, no publicado',
        );
    });

    it('el embudo v1 sigue declarando explícitamente lo que NO incluye', () => {
        const page = readSource('app/(public)/metodologia/page.tsx');
        assert.ok(
            page.includes('Lo que v1 NO incluye todavía:'),
            'tripwire: la declaración de límites de v1 no debe desaparecer',
        );
    });

    it('la tarjeta «Sobre ProPicks IA» no lista capacidades ausentes en v1', () => {
        const card = readSource('components/proPicks/EnhancedProPicksContent.tsx');
        assert.ok(!card.includes('✓ Evaluación de momentum'), 'momentum no se lista como capacidad actual');
        assert.ok(!card.includes('✓ Comparación con sector'), 'el ranking es por percentiles del universo, no por sector');
        assert.ok(!card.includes('compara cada acción con su sector'), 'sin comparación sectorial prometida');
        assert.ok(
            card.includes('✗ Valoración y momentum: aún no (v1)'),
            'la tarjeta declara explícitamente lo que v1 no incluye',
        );
        assert.ok(card.includes('✓ Ranking por percentiles del universo'), 'capacidad real declarada');
    });
});

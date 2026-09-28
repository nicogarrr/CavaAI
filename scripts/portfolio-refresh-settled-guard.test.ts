/**
 * refreshPortfolioHoldings con allSettled:
 *  - A guardado + B fallida => updated=[A], failed=[B], la caché se invalida
 *    igualmente y el resultado declara qué se guardó y qué falló.
 *  - Escritura OK + relectura KO => holdingsStale, nunca un error que
 *    sugiriera que no se escribió nada.
 * Ejecución: node --experimental-strip-types --test scripts/portfolio-refresh-settled-guard.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
// Node (strip-types) exige la extension .ts en runtime; tsc la rechaza
// sin allowImportingTsExtensions. El guard se ejecuta con node, no con tsc.
// @ts-expect-error - import runtime de node
import { partitionSettledRefreshes } from '../lib/portfolio/refresh-settled.ts';

const here = dirname(fileURLToPath(import.meta.url));
const source = (rel: string) => readFileSync(join(here, '..', rel), 'utf8');

void test('A guardada y B rechazada: A cuenta como escrita, B como fallida', () => {
    const { updated, skipped, failed } = partitionSettledRefreshes(
        ['A', 'B'],
        [
            { status: 'fulfilled', value: { symbol: 'A', written: true } },
            { status: 'rejected' },
        ],
    );
    assert.deepEqual(updated, ['A']);
    assert.deepEqual(skipped, []);
    assert.deepEqual(failed, ['B']);
});

void test('sin cotización no es escritura fallida', () => {
    const { updated, skipped, failed } = partitionSettledRefreshes(
        ['A', 'B', 'C'],
        [
            { status: 'fulfilled', value: { symbol: 'A', written: true } },
            { status: 'fulfilled', value: { symbol: 'B', written: false } },
            { status: 'rejected' },
        ],
    );
    assert.deepEqual(updated, ['A']);
    assert.deepEqual(skipped, ['B']);
    assert.deepEqual(failed, ['C']);
});

void test('todas rechazadas: failed las declara una a una', () => {
    const { updated, failed } = partitionSettledRefreshes(
        ['A', 'B'],
        [{ status: 'rejected' }, { status: 'rejected' }],
    );
    assert.deepEqual(updated, []);
    assert.deepEqual(failed, ['A', 'B']);
});

void test('la acción usa allSettled e invalida con al menos una escritura', () => {
    const actions = source('lib/actions/portfolio.actions.ts');
    assert.ok(actions.includes('Promise.allSettled'), 'allSettled en el bucle de escritura');
    assert.ok(actions.includes('partitionSettledRefreshes'), 'partición discriminada');
    const invalidateAt = actions.indexOf('invalidatePortfolioReads(user.id);');
    const rereadAt = actions.indexOf('getPortfolioSummary(user.id)).holdings');
    assert.ok(invalidateAt > -1 && rereadAt > -1 && invalidateAt < rereadAt, 'invalida SIEMPRE antes de releer');
    assert.ok(actions.includes('holdingsStale'), 'relectura fallida tras escritura declarada');
});

/**
 * Guard del helper de lotes del índice /research: un lote fallido queda
 * aislado (null en su posición) y no degrada los demás.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { fetchInBatches } from '../lib/research/snapshots.ts';

test('trocea en lotes del tamaño pedido y conserva el orden', async () => {
    const seen: string[][] = [];
    const result = await fetchInBatches(['A', 'B', 'C', 'D', 'E'], 2, async (batch) => {
        seen.push(batch);
        return batch.join('');
    });
    assert.deepEqual(seen, [['A', 'B'], ['C', 'D'], ['E']]);
    assert.deepEqual(result, ['AB', 'CD', 'E']);
});

test('un lote fallido queda aislado y no borra los demás', async () => {
    const result = await fetchInBatches(['A', 'B', 'C', 'D', 'E'], 2, async (batch) => {
        if (batch.includes('C')) throw new Error('backend intermitente');
        return batch.join('');
    });
    assert.deepEqual(result, ['AB', null, 'E']);
});

test('con todos los lotes fallidos devuelve todos null (sin lanzar)', async () => {
    const result = await fetchInBatches(['A', 'B'], 1, async () => {
        throw new Error('caído');
    });
    assert.deepEqual(result, [null, null]);
});

test('entrada vacía no llama al fetcher', async () => {
    let calls = 0;
    const result = await fetchInBatches([], 50, async () => {
        calls += 1;
        return 'x';
    });
    assert.deepEqual(result, []);
    assert.equal(calls, 0);
});

/**
 * signalKey distingue dos compras codigo P del mismo insider en la misma
 * fecha/form/fichero (lotes distintos): accession+line (identidad estable del
 * backend) y, como respaldo, los campos de ejecucion (shares/price/value).
 * Con la clave compartida, React reutilizaba la fila de OTRA compra.
 * Ejecución: node --experimental-strip-types --test scripts/insider-signal-key-guard.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const source = (rel: string) => readFileSync(join(here, '..', rel), 'utf8');

void test('la clave incluye accession, linea y campos de ejecucion', () => {
    const view = source('components/insider/InsiderSignalsView.tsx');
    assert.ok(view.includes('signal.accession_number'), 'accession en la clave');
    assert.ok(view.includes('signal.tx_line'), 'ordinal de linea en la clave');
    assert.ok(view.includes('signal.shares'), 'shares en la clave');
    assert.ok(view.includes('signal.price'), 'price en la clave');
    assert.ok(view.includes('signal.value'), 'value en la clave');
});

void test('el backend emite la identidad por transaccion en las senales', () => {
    const service = source('data-engine/app/services/insider_service.py');
    assert.ok(service.includes('tx["tx_line"] = line_index'), 'ordinal por filing');
    const big = service.indexOf('"signal": "big_buy"');
    const cSuite = service.indexOf('"signal": "c_suite_buy"');
    for (const at of [big, cSuite]) {
        const block = service.slice(at, at + 900);
        assert.ok(block.includes('"accession_number": tx.get("accession_number")'), 'accession en la senal');
        assert.ok(block.includes('"tx_line": tx.get("tx_line")'), 'linea en la senal');
    }
});

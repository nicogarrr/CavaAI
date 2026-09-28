import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const workers = readFileSync('data-engine/app/workers/dramatiq_app.py', 'utf8');
const compose = readFileSync('docker-compose.prod.yml', 'utf8');

// F359 (reporte de usuario): "Generar tesis" mostraba "En cola" pero el job
// no arrancaba nunca - la cola default estaba envenenada (7476 mensajes,
// 5276 de ingesta SEC imposible desde OCI) y los jobs de usuario quedaban
// hambreados. Los jobs interactivos de tesis van en cola dedicada.
test('F359: generate_thesis_job va en la cola dedicada "thesis" y el worker la escucha', () => {
    assert.match(workers, /@dramatiq\.actor\(max_retries=2, min_backoff=15_000, queue_name="thesis"\)\ndef generate_thesis_job/);
    assert.match(compose, /"-Q", "default", "prices", "thesis"/);
});

test('F359: SEC 403/429 (bloqueo permanente de IPs OCI) no se reintenta', () => {
    assert.match(workers, /if status in \(403, 429\) and "sec\.gov" in str\(exc\)/);
    assert.match(workers, /return False[\s\S]{0,400}return status is not None and \(status == 429 or status >= 500\)/);
});

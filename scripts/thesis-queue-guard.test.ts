import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const workers = readFileSync('data-engine/app/workers/dramatiq_app.py', 'utf8');
const compose = readFileSync('docker-compose.prod.yml', 'utf8');

// F359 (reporte de usuario): "Generar tesis" mostraba "En cola" pero el job
// no arrancaba nunca - la cola default estaba envenenada (7476 mensajes,
// 5276 de ingesta SEC imposible desde OCI) y los jobs de usuario quedaban
// hambreados. Los jobs interactivos de tesis van en cola dedicada.
test('F359: la tesis va en cola dedicada consumida por un worker DEDICADO', () => {
    assert.match(workers, /@dramatiq\.actor\(max_retries=2, min_backoff=15_000, queue_name="thesis"\)\ndef generate_thesis_job/);
    // Servicio aparte con sus propios hilos: compartir proceso con
    // default/prices dejaba la tesis hambreada (exigencia del auditor).
    assert.match(compose, /worker-thesis:[\s\S]{0,900}"-Q", "thesis"/);
    const workerCmd = compose.match(/worker:\n[\s\S]{0,200}command: \[[^\]]*\]/)?.[0] ?? '';
    assert.ok(workerCmd && !workerCmd.includes('thesis'), 'el worker general NO consume thesis');
});

test('F359: SEC 403 es permanente; 429 SEC se reintenta acotado con circuit breaker por origen', () => {
    assert.match(workers, /if status == 403 and "sec\.gov" in str\(exc\)/, '403 SEC = permanente');
    assert.match(workers, /if status == 429 and "sec\.gov" in str\(exc\)[\s\S]{0,600}_sec_rate_limit_allows_retry\(\)/, '429 SEC = breaker');
    assert.match(workers, /_SEC_429_STREAK_LIMIT = 5/);
    assert.match(workers, /_sec_429_open_until = current \+ _SEC_429_COOLDOWN_S/, 'el breaker abre con cooldown');
    assert.match(workers, /return status is not None and \(status == 429 or status >= 500\)/, '429/5xx generico sigue reintentable');
});

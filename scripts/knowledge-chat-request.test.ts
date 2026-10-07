import assert from 'node:assert/strict';
import { register } from 'node:module';
import { afterEach, test } from 'node:test';

register('./research-client-contract.loader.mjs', import.meta.url);
// @ts-expect-error TS5097: node --experimental-strip-types necesita extensión explícita.
const { askKnowledge } = await import('../lib/actions/knowledge-chat.actions.ts');
// @ts-expect-error TS5097: extensión explícita de Node.
const { AppError } = await import('../lib/types/errors.ts');
const savedFetch = globalThis.fetch;
const savedTimeout = AbortSignal.timeout;
afterEach(() => { globalThis.fetch = savedFetch; AbortSignal.timeout = savedTimeout; });

test('chat POST tiene 60s explícitos y request abortable, sin retry de POST', async () => {
  let calls = 0;
  let budget = 0;
  AbortSignal.timeout = (ms: number) => { budget = ms; return savedTimeout(5); };
  globalThis.fetch = (async (_url: RequestInfo | URL, init?: RequestInit) => {
    calls++;
    assert.equal(init?.method, 'POST');
    const signal = init?.signal;
    assert.ok(signal);
    return new Promise<Response>((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(signal.reason), { once: true });
      setTimeout(() => {}, 15); // Mantiene vivo el proceso hasta que dispare AbortSignal.timeout.
    });
  }) as typeof fetch;
  await assert.rejects(askKnowledge('recompras', 'letters'), /timeout de 60000 ms/);
  assert.equal(budget, 60_000);
  assert.equal(calls, 1);
});

test('conserva error de sesión API 401, sin convertirlo en éxito o mensaje genérico', async () => {
  globalThis.fetch = (async () => new Response(JSON.stringify({ detail: 'Sesión caducada' }), {
    status: 401, headers: { 'Content-Type': 'application/json' },
  })) as typeof fetch;
  await assert.rejects(askKnowledge('recompras', 'letters'), (error: unknown) => {
    assert.ok(error instanceof AppError);
    assert.equal(error.statusCode, 401);
    assert.equal(error.code, 'RESEARCH_API_ERROR');
    assert.equal(error.message, 'Sesión caducada');
    return true;
  });
});

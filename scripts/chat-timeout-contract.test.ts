/** Real server-action/client code, synthetic identity, loopback HTTP only. */
import { it, after } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
register('./research-client-contract.loader.mjs', import.meta.url);
const server = createServer((req, res) => {
  let body = '';
  req.on('data', chunk => { body += chunk; });
  req.on('end', () => {
    assert.equal(req.url, '/api/chat');
    assert.equal(req.headers['x-cavaai-user'], 'contract-test-user');
    assert.equal(JSON.parse(body).question, 'Que es el per?');
    setTimeout(() => {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ answer: 'El PER relaciona precio y beneficio por acción.', blocked: false, proposed_actions: [], sources: [] }));
    }, 16_000);
  });
});
await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
const addr = server.address();
assert.ok(addr && typeof addr !== 'string');
process.env.FMP_BACKEND_URL = `http://127.0.0.1:${addr.port}`;
// @ts-expect-error Node strip-types requires explicit extension.
const { chatWithPortfolio } = await import('../lib/actions/chat.actions.ts');
// @ts-expect-error Node strip-types requires explicit extension.
const { researchTimeoutFor } = await import('../lib/research/client.ts');
const realFetch = globalThis.fetch;
after(() => { globalThis.fetch = realFetch; server.closeAllConnections(); server.close(); });
it('chat budget fits 45s LLM plus overhead, within 60s action', () => {
  assert.equal(researchTimeoutFor('/api/chat', 'POST'), 55_000);
  assert.equal(researchTimeoutFor('/api/chat', 'GET'), 15_000);
  assert.equal(researchTimeoutFor('/api/portfolio/summary', 'GET'), 8_000);
  assert.equal(researchTimeoutFor('/api/chat', 'POST', { timeoutMs: 7 }), 7);
  for (const path of ['app/(root)/portfolio/page.tsx', 'app/(root)/research/[ticker]/page.tsx']) {
    assert.match(readFileSync(path, 'utf8'), /export const maxDuration = 60/);
  }
});
it('real portfolio action accepts loopback response after the old 15s cutoff', { timeout: 25_000 }, async () => {
  const started = performance.now();
  const result = await chatWithPortfolio('Que es el per?', 'contract-test-user');
  assert.ok(performance.now() - started >= 15_000);
  assert.equal(result.success, true);
  assert.match(result.message, /PER/);
});
it('keeps owner check before sending requests', async () => {
  await assert.rejects(chatWithPortfolio('Que es el per?', 'another-user'), /another user/);
});
it('returns timeout as Spanish recoverable result, not hidden server exception', async () => {
  globalThis.fetch = (async () => { throw new DOMException('Timed out', 'TimeoutError'); }) as typeof fetch;
  try {
    const result = await chatWithPortfolio('Que es el per?', 'contract-test-user');
    assert.equal(result.success, false);
    assert.match(result.message, /tarda más de lo normal.*Reinténtalo/);
  } finally { globalThis.fetch = realFetch; }
});
it('distinguishes network outage without leaking diagnostics', async () => {
  globalThis.fetch = (async () => { throw new TypeError('secret internal host'); }) as typeof fetch;
  try {
    const result = await chatWithPortfolio('Que es el per?', 'contract-test-user');
    assert.equal(result.success, false);
    assert.match(result.message, /no está disponible ahora/);
    assert.doesNotMatch(result.message, /secret/);
  } finally { globalThis.fetch = realFetch; }
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
// @ts-expect-error TS5097: explicit extension for node strip-types.
import { sanitizeDebate, sanitizeLlmText } from '../lib/research/debate-sanitize.ts';

assert.equal(sanitizeLlmText('Caso 上行 alcista\u200b\u0007 ok'), 'Caso alcista ok');
assert.equal(sanitizeLlmText(42), '');
assert.equal(sanitizeLlmText('a'.repeat(9000)).length, 6000);
assert.equal(sanitizeDebate(null), null);
assert.equal(sanitizeDebate({ bull_case: '', bear_case: '', verdict_rationale: '' }), null);
const d = sanitizeDebate({
    ticker: 'ASTS', bull_case: 'Bull 한국어 ok', bear_case: 'Bear', verdict: 'moon',
    verdict_rationale: 'x', llm_calls: 2.7, degraded: 'yes', model: 'm',
});
assert.ok(d);
assert.equal(d.bull_case, 'Bull ok');
assert.equal(d.verdict, 'neutral');
assert.equal(d.llm_calls, 2);
assert.equal(d.degraded, false);

const action = readFileSync('lib/actions/thesis-jobs.actions.ts', 'utf8');
const body = action.slice(action.indexOf('export async function runThesisDebate'), action.indexOf('export interface ThesisApproval'));
assert.ok(/timeoutMs: DEBATE_TIMEOUT_MS/.test(body), 'debate needs its own timeout');
assert.ok(!/\bthrow\b/.test(body), 'runThesisDebate must not throw (React #441 in prod)');
assert.ok(/sanitizeDebate\(raw\)/.test(body), 'LLM output must be sanitized');
console.log('debate-sanitize-guard ok');

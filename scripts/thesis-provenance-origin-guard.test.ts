import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const memo = readFileSync('components/research/ThesisMemo.tsx', 'utf8');

test('OFICIAL inputs link to the official source and carry no inference mark', () => {
  assert.match(memo, /isVerifiedOficial\(item\) \? null/);
  assert.match(memo, /href=\{fuente\.url\}/);
  assert.match(memo, /rel="noopener noreferrer"/);
});

test('INFERIDO inputs show the mark, the explicit base and only https links', () => {
  assert.match(memo, /INFERIDO/);
  assert.match(memo, /dado \$\{item\.base_inferencia\}/);
  assert.match(memo, /base no documentada/);
  assert.ok((memo.match(/\^https:/g) ?? []).length >= 2);
});

test('render is fail-closed: no derivado/supuesto/estimacion badges, legacy payloads show INFERIDO', () => {
  assert.doesNotMatch(memo, /PROVENANCE_BADGES/);
  assert.doesNotMatch(memo, /estimación LLM/);
  assert.match(memo, /function isVerifiedOficial/);
  assert.match(memo, /f\.oficial && !!f\.fecha/);
  assert.match(memo, /item\.base_documentada !== true/);
});

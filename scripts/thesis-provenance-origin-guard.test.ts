import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const memo = readFileSync('components/research/ThesisMemo.tsx', 'utf8');

test('OFICIAL inputs link to the official source and carry no inference mark', () => {
  assert.match(memo, /item\.origen === 'OFICIAL' \? null/);
  assert.match(memo, /href=\{fuente\.url\}/);
  assert.match(memo, /rel="noopener noreferrer"/);
});

test('INFERIDO inputs show the mark, the explicit base and only https links', () => {
  assert.match(memo, /'INFERIDO'/);
  assert.match(memo, /dado \$\{item\.base_inferencia\}/);
  assert.match(memo, /base no documentada/);
  assert.ok((memo.match(/\^https:/g) ?? []).length >= 2);
});

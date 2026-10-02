import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const flow = readFileSync('components/research/NewsEventsFlow.tsx', 'utf8');
const page = readFileSync('app/(root)/research/news/page.tsx', 'utf8');
const actions = readFileSync('lib/actions/research.actions.ts', 'utf8');
const route = readFileSync('data-engine/app/api/routes/news.py', 'utf8');

test('el flujo de noticias pagina con scroll infinito y boton de respaldo', () => {
  assert.match(flow, /IntersectionObserver/);
  assert.match(flow, /loadMoreResearchNews/);
  assert.match(flow, /Cargar más/);
  assert.match(flow, /role="alert"/);
});

test('la primera pagina y el carril se piden al servidor, no se filtran en cliente', () => {
  assert.match(page, /getResearchNews\(lane, 0, NEWS_PAGE_SIZE\)/);
  assert.doesNotMatch(page, /events\.filter\(/);
  assert.match(actions, /export async function loadMoreResearchNews/);
});

test('la API acota limit/offset y filtra el carril en SQL', () => {
  assert.match(route, /Annotated\[int, Query\(ge=1, le=100\)\] = 100/);
  assert.match(route, /offset: Annotated\[int, Query\(ge=0\)\] = 0/);
  assert.match(route, /lane: Literal\["empresa", "macro"\]/);
});

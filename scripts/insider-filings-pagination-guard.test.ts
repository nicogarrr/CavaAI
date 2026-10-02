import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const view = readFileSync('components/insider/InsiderSignalsView.tsx', 'utf8');
const actions = readFileSync('lib/actions/insider.actions.ts', 'utf8');
const route = readFileSync('data-engine/app/api/routes/insider.py', 'utf8');

test('filings persistidos: cargar más, total honesto y sin recorte silencioso a 10', () => {
  assert.doesNotMatch(view, /filings\.slice\(0, 10\)/);
  assert.match(view, /Cargar más/);
  assert.match(view, /Mostrando \{filings\.length\} de \{filingsTotal\}/);
  assert.match(view, /initialFilings\.total \?\? initialFilings\.count/);
});

test('la acción y la API paginan por offset y devuelven el total', () => {
  assert.match(actions, /export async function loadMoreInsiderFilings/);
  assert.match(route, /offset: Annotated\[int, Query\(ge=0\)\] = 0/);
  assert.match(route, /"total": total/);
});

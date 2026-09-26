import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

// F73: la fecha de un evento es la de publicación de la fuente, no la de
// ingesta; y el razonamiento interno de scoring no se pinta en la UI.

const here = dirname(fileURLToPath(import.meta.url));
const source = (rel: string) => readFileSync(join(here, '..', rel), 'utf8');

void test('la ingesta preserva published_at de la fuente', () => {
  const service = source('data-engine/app/services/news_service.py');
  assert.ok(service.includes('date=published_at or datetime.now(UTC)'), 'date debe venir de la fuente');
  assert.ok(service.includes('published_at=item.published_at'), 'el pipeline pasa la fecha del item');
});

void test('la UI no pinta el razonamiento interno de scoring', () => {
  const page = source('app/(root)/research/news/page.tsx');
  assert.ok(!page.includes('materiality_reasons'), 'materiality_reasons fuera de la UI');
});

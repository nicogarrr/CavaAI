import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

// F91: el contexto de cartera de /research no puede pintar los importes con
// una moneda inventada ('USD' fijo): usa la base_currency del backend o NA.

const here = dirname(fileURLToPath(import.meta.url));
const source = (rel: string) => readFileSync(join(here, '..', rel), 'utf8');

void test('los importes del contexto de cartera usan la moneda base del backend', () => {
  const page = source('app/(root)/research/page.tsx');
  assert.ok(!page.includes("formatMoney(value, 'USD'"), 'moneda fija USD prohibida');
  assert.ok(page.includes('portfolio.base_currency'), 'usa la moneda base del summary');
});

void test('sin moneda base no se inventa símbolo: NA honesto', () => {
  const page = source('app/(root)/research/page.tsx');
  const money = page.slice(page.indexOf('function money('), page.indexOf('}', page.indexOf('function money(')) + 1);
  assert.ok(money.includes(': NA'), 'sin moneda base -> NA');
  const type = source('lib/actions/research.actions.ts');
  assert.ok(type.includes('base_currency?: string'), 'el tipo declara base_currency');
});

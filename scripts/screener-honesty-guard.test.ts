/**
 * Guarda de honestidad del screener (F63/F223/F97):
 *  - Los botones de sector deben usar los nombres GICS que el backend sirve
 *    ('Information Technology', 'Financials', ...). Filtrar por un nombre que
 *    el backend no conoce devuelve 0 filas y el primer pintado salía vacío.
 *  - Un marketCap 0 (proveedor sin perfil) no puede formatearse como si fuera
 *    una capitalización real: se muestra N/D.
 *  - El backend debe poder pedir el perfil a un vendor que sí lo sirva
 *    (resolve_profile_vendor) aunque las cotizaciones vengan de otro.
 * Ejecución: node --experimental-strip-types --test scripts/screener-honesty-guard.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const source = (rel: string) => readFileSync(join(here, '..', rel), 'utf8');

void test('los sectores del screener son los GICS que sirve el backend', () => {
    const page = source('app/(root)/screener/page.tsx');
    assert.ok(page.includes("'Information Technology'"), 'sector por defecto servido por el backend');
    assert.ok(page.includes("'Financials'"), 'GICS Financials');
    assert.ok(page.includes("'Consumer Discretionary'"), 'GICS Consumer Discretionary');
    assert.ok(!page.includes("{ en: 'Technology' }"), 'Technology no es un sector servido: filtrar por él da 0 filas');
    assert.ok(!page.includes("{ en: 'Financial Services' }"), 'Financial Services no es un sector servido');
    assert.ok(!page.includes("{ en: 'Consumer Cyclical' }"), 'Consumer Cyclical no es un sector servido');
});

void test('un marketCap ausente (0) se muestra como N/D, no formateado', () => {
    const page = source('app/(root)/screener/page.tsx');
    assert.ok(page.includes('r.marketCap > 0'), 'guarda de marketCap positivo antes de formatear');
});

void test('el backend resuelve un vendor de perfil cuando el de cotizaciones no lo tiene', () => {
    const backend = source('data-engine/app/api/routes/screeners.py');
    assert.ok(backend.includes('resolve_profile_vendor'), 'helper de vendor de perfil presente');
    assert.ok(backend.includes('supports_profiles'), 'el Protocol declara si el vendor sirve perfiles');
});

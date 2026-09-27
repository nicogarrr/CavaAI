/**
 * F179: el indice de /research se titula «Todas las empresas con research en
 * CavaAI», pero el listado salia de UNA llamada a /api/companies, cuyo
 * default es 100 fichas (tope 500). Con mas de 100 empresas el indice se
 * cortaba en silencio (A→AMBA) y «todas» mentia. El dashboard debe pedir
 * TODAS las paginas; este guard fija ese contrato.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const actions = readFileSync('lib/actions/research.actions.ts', 'utf8');

function dashboardBody() {
    const start = actions.indexOf('export async function getResearchDashboard()');
    assert.notEqual(start, -1, 'getResearchDashboard debe existir');
    return actions.slice(start);
}

test('el dashboard no pide /api/companies a pelo (default 100)', () => {
    const body = dashboardBody();
    assert.ok(
        !body.includes("getJson<ResearchCompany[]>('/api/companies'"),
        'una llamada sin limit/offset lista solo las 100 primeras empresas',
    );
});

test('el listado se completa paginando hasta una pagina corta', () => {
    assert.match(actions, /getAllResearchCompanies/);
    assert.match(actions, /offset=\$\{offset\}/);
    assert.match(actions, /if \(page\.length < COMPANIES_PAGE_SIZE\) return all;/);
});

test('la pagina pedida respeta el tope del backend (limit le=500)', () => {
    const match = actions.match(/const COMPANIES_PAGE_SIZE = (\d+);/);
    assert.ok(match, 'COMPANIES_PAGE_SIZE debe existir');
    assert.ok(Number(match[1]) <= 500, 'el backend rechaza limit > 500');
});

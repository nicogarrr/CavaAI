/**
 * Quick win UX 3: nav limpio. Sin duplicados Plan/Mi plan ni Ayuda x2, sin
 * /research/workflows en el árbol principal y «Vista de mercado» renombrada
 * a «Mercado».
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const constants = readFileSync('lib/constants.ts', 'utf8');
const sidebar = readFileSync('components/layout/Sidebar.tsx', 'utf8');
const breadcrumbs = readFileSync('components/layout/Breadcrumbs.tsx', 'utf8');

test('cada destino del sidebar aparece una sola vez (árbol + pie)', () => {
    // /plan y /help tenían entrada en NAV_SECTIONS Y en el pie del sidebar.
    assert.ok(!sidebar.includes('FooterLink href="/plan"'), '/plan duplicado en el pie del sidebar');
    assert.ok(!sidebar.includes('FooterLink href="/help"'), '/help duplicado en el pie del sidebar');
    // /security no está en el árbol: su pie se mantiene.
    assert.match(sidebar, /FooterLink href="\/security"/);
    // En el árbol, cada href una vez.
    const tree = constants.slice(constants.indexOf('export const NAV_SECTIONS'), constants.indexOf('export function flattenNavItems'));
    for (const href of ['/plan', '/help', '/export']) {
        const occurrences = tree.split(`href: '${href}'`).length - 1;
        assert.equal(occurrences, 1, `${href} debe aparecer exactamente una vez en NAV_SECTIONS`);
    }
});

test('la sección del plan tiene un solo destino: sin título duplicado', () => {
    // «Mi plan» con un solo item no muestra título (showsNavSectionTitle) y
    // el nav deja de leer «Mi plan / Plan» seguidos.
    const section = /title: 'Mi plan',\s*\n\s*items: \[([\s\S]*?)\],\s*\n\s*\}/.exec(constants);
    assert.ok(section, 'sección Mi plan no encontrada');
    assert.equal((section[1].match(/href:/g) ?? []).length, 1);
    assert.match(constants, /export function showsNavSectionTitle[\s\S]*?section\.items\.length > 1/);
});

test('/research/workflows fuera del árbol principal, miga legible', () => {
    assert.ok(!constants.includes("'/research/workflows'"), 'Workflows no debe estar en NAV_SECTIONS');
    // La página sigue existiendo y su miga no sale cruda.
    assert.match(breadcrumbs, /'workflows': 'Workflows'/);
});

test('«Vista de mercado» pasa a «Mercado»', () => {
    assert.ok(!constants.includes('Vista de mercado'), 'queda el nombre antiguo');
    assert.match(constants, /\{ href: '\/screener', label: 'Mercado', icon: LineChart \}/);
});

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
    assert.ok(!sidebar.includes('FooterLink href="/security"'));
    assert.ok(readFileSync("components/UserDropdown.tsx", "utf8").includes('router.push("/security")'));
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

test('el árbol del sidebar encoge con min-h-0: el pie queda alcanzable', () => {
    // Sin min-h-0 en un flex-col, el nav no encoge por debajo de su
    // contenido: el aside supera h-dvh y el pie (Seguridad) cae bajo el
    // fold sin scroll interno en viewports bajos.
    const sidebar = readFileSync('components/layout/Sidebar.tsx', 'utf8');
    assert.match(sidebar, /min-h-0 flex-1 overflow-y-auto/);
});

test('el alto del aside descuenta la zona pegajosa (h-dvh a secas destierra el pie)', () => {
    // Con h-dvh y top-0 el aside mide el viewport entero empezando debajo
    // del header a scroll 0: sus ultimos --shell-top px caen bajo el fold.
    // El alto correcto es 100dvh - --shell-top anclado a top: --shell-top.
    assert.match(sidebar, /top-\[var\(--shell-top\)\]/);
    assert.match(sidebar, /h-\[calc\(100dvh-var\(--shell-top\)\)\]/);
});

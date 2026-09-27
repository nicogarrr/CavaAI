/**
 * F176 (resto tablet): la tabla de /research/news cabe en su scroller pero en
 * táctil no había affordance de scroll — scrollbar overlay invisible y
 * titulares cortados a media palabra sin que el usuario supiera que existen
 * más columnas. La affordance es CSS pura (.scroll-affordance-x: scrollbar
 * visible + sombras de borde que solo aparecen cuando hay contenido oculto),
 * así que no puede anunciar scroll inexistente. /watchlist ya mostraba
 * scrollbar visible en tablet.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync('app/(root)/research/news/page.tsx', 'utf8');
const css = readFileSync('app/globals.css', 'utf8');

test('la región de la tabla de noticias lleva la affordance de scroll', () => {
    assert.match(page, /scroll-affordance-x overflow-x-auto \[contain:layout_paint\]/);
});

test('la affordance es doble: scrollbar visible y sombras de scroll', () => {
    const block = css.slice(css.indexOf('.scroll-affordance-x'));
    assert.match(block, /scrollbar-width: thin;/);
    assert.match(block, /background-attachment: local, local, scroll, scroll;/);
    // Las sombras deben desaparecer al llegar al borde: es la técnica de
    // gradientes locales, no un aviso fijo que mentiría sin overflow.
    assert.match(block, /linear-gradient\(to right/);
    assert.match(block, /linear-gradient\(to left/);
});

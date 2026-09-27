import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const tabs = readFileSync('components/portfolio/PortfolioTabs.tsx', 'utf8');
const landing = readFileSync('components/landing/PublicLanding.tsx', 'utf8');

test('F289: el texto del banner de /portfolio salta a su propia fila antes de colapsar', () => {
    // flex-1 sin basis dejaba al <p> con ~50px en 768px (sidebar + dos enlaces):
    // con basis-60 el navegador lo envuelve a una fila completa por debajo de
    // 240px en vez de comprimirlo.
    assert.match(tabs, /<p className="min-w-0 flex-1 basis-60 text-sm text-gray-400">/);
});

test('F285: los CTAs del hero envuelven en sm en vez de desbordar a 768px', () => {
    // Los Button llevan whitespace-nowrap + shrink-0: en una fila sm sin wrap
    // la suma supera 768px (scrollWidth 847). flex-wrap manda el segundo CTA
    // a la siguiente línea.
    assert.match(landing, /mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center/);
});

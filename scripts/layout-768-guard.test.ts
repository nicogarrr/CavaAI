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

test('F290: los KPIs de /portfolio dimensionan por ancho de contenido (sidebar en md)', () => {
    // grid-cols-2 md:grid-cols-4 asumía viewport≈contenido: con el sidebar de
    // 15rem visible desde md, a 768px el contenido son ~31rem y 4 columnas
    // dejaban ~7rem por tarjeta (valores clipados, 4ª fuera del borde).
    // auto-fit+minmax(12rem) colapsa a 2 columnas hasta que cada tarjeta
    // tiene sitio real (~1280px con sidebar), sin tocar el móvil (<sm sigue
    // en 2 columnas, verificado por QA).
    const summary = readFileSync('components/portfolio/PortfolioSummary.tsx', 'utf8');
    assert.match(summary, /grid grid-cols-2 gap-3 sm:gap-4 sm:\[grid-template-columns:repeat\(auto-fit,minmax\(12rem,1fr\)\)\]/);
    assert.doesNotMatch(summary, /md:grid-cols-4/);
});

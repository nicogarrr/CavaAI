import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const chat = readFileSync('components/portfolio/PortfolioChat.tsx', 'utf8');
const allocation = readFileSync('components/portfolio/PortfolioAllocation.tsx', 'utf8');

test('F339: la burbuja se auto-oculta durante el scroll y reaparece ~600 ms después', () => {
    assert.match(chat, /addEventListener\('scroll', onScroll, \{ passive: true, capture: true \}\)/);
    assert.match(chat, /setFabScrollHidden\(true\)/);
    assert.match(chat, /setTimeout\(\(\) => \{\s*setFabScrollHidden\(false\);\s*checkLegendOverlap\(\);\s*\}, 600\)/);
});

test('F339: en reposo la burbuja queda oculta mientras la leyenda intersecta su zona', () => {
    // El solape de F339 ocurre con el scroll parado: solo auto-ocultar durante
    // el scroll devuelve la burbuja 600 ms después, justo cuando el usuario se
    // detiene a leer el donut. La burbuja también se oculta siempre que la
    // leyenda (por id) cruce la banda de 96px abajo-derecha del viewport.
    assert.match(chat, /getElementById\('portfolio-allocation-legend'\)/);
    assert.match(chat, /window\.innerWidth - 96/);
    assert.match(chat, /window\.innerHeight - 96/);
    assert.match(chat, /setFabLegendBlocked\(/);
    assert.match(chat, /fabScrollHidden \|\| fabLegendBlocked/);
    assert.match(allocation, /id="portfolio-allocation-legend"/);
});

test('F339: la zona se calcula desde el viewport, no del rect del botón (sin oscilación)', () => {
    // Con translate-y-24 el rect del propio FAB saldría de la zona al ocultarse
    // y la burbuja parpadearía; la zona deriva de innerWidth/innerHeight.
    assert.doesNotMatch(chat, /fabRef/);
    assert.match(chat, /addEventListener\('resize', checkLegendOverlap/);
});

test('F339: la leyenda se re-consulta por id (las tabs la montan y desmontan)', () => {
    // Si la leyenda no existe en el DOM (otra tab activa), no hay bloqueo.
    assert.match(chat, /if \(!legend\) \{\s*setFabLegendBlocked\(false\);\s*return;\s*\}/);
});

test('F339: la burbuja oculta no intercepta toques, md+ la mantiene visible y todo se limpia', () => {
    assert.match(chat, /translate-y-24 opacity-0 pointer-events-none md:translate-y-0 md:opacity-100 md:pointer-events-auto/);
    assert.match(chat, /removeEventListener\('scroll', onScroll, \{ capture: true \}\)/);
    assert.match(chat, /removeEventListener\('resize', checkLegendOverlap\)/);
    assert.match(chat, /clearTimeout\(timer\)/);
});

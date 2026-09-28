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
    // detiene a leer el donut.
    assert.match(chat, /getElementById\('portfolio-allocation-legend'\)/);
    assert.match(chat, /setFabLegendBlocked\(/);
    assert.match(chat, /fabScrollHidden \|\| fabLegendBlocked/);
    assert.match(allocation, /id="portfolio-allocation-legend"/);
});

test('F339: la zona se mide por computed style (safe-area iPhone incluida, sin oscilación)', () => {
    // bottom/right del computed style resuelven env(safe-area-inset-*) a px y no
    // dependen del transform: con translate-y-24 el rect saldría de la zona y la
    // burbuja parpadearía. La banda no es una constante: cubre el inset real.
    assert.match(chat, /getComputedStyle\(fab\)/);
    assert.match(chat, /parseFloat\(styles\.bottom\)/);
    assert.match(chat, /parseFloat\(styles\.right\)/);
    assert.doesNotMatch(chat, /innerWidth - 96/);
    assert.doesNotMatch(chat, /innerHeight - 96/);
});

test('F339: un cambio de tab re-ejecuta el chequeo aunque no haya scroll ni resize', () => {
    // Las tabs montan/desmontan la leyenda sin scroll: sin MutationObserver el
    // estado queda obsoleto (FAB tapando la leyenda recién montada u oculto
    // para siempre tras desmontarla).
    assert.match(chat, /new MutationObserver\(checkLegendOverlap\)/);
    assert.match(chat, /observer\.observe\(document\.body, \{ childList: true, subtree: true \}\)/);
    assert.match(chat, /observer\.disconnect\(\)/);
    assert.match(chat, /if \(!legend \|\| !fab\) \{\s*setFabLegendBlocked\(false\);\s*return;\s*\}/);
});

test('F339: la burbuja oculta no intercepta toques, md+ la mantiene visible y todo se limpia', () => {
    assert.match(chat, /translate-y-24 opacity-0 pointer-events-none md:translate-y-0 md:opacity-100 md:pointer-events-auto/);
    assert.match(chat, /removeEventListener\('scroll', onScroll, \{ capture: true \}\)/);
    assert.match(chat, /removeEventListener\('resize', checkLegendOverlap\)/);
    assert.match(chat, /clearTimeout\(timer\)/);
});

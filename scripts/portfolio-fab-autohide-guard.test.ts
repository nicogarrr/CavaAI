import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const chat = readFileSync('components/portfolio/PortfolioChat.tsx', 'utf8');

test('F339: la burbuja del chat se auto-oculta durante el scroll y reaparece ~600 ms después', () => {
    // A 390px el FAB (fixed bottom-right) tapa la columna de porcentajes de la
    // leyenda del donut de Distribución en cualquier punto de reposo del scroll.
    assert.match(chat, /addEventListener\('scroll', onScroll, \{ passive: true, capture: true \}\)/);
    assert.match(chat, /setFabHidden\(true\)/);
    assert.match(chat, /setTimeout\(\(\) => setFabHidden\(false\), 600\)/);
});

test('F339: la burbuja oculta no intercepta toques y md+ la mantiene visible', () => {
    // El solape es móvil; desktop queda intacto vía clases md:*.
    assert.match(chat, /translate-y-24 opacity-0 pointer-events-none md:translate-y-0 md:opacity-100 md:pointer-events-auto/);
});

test('F339: el listener de scroll se limpia al desmontar', () => {
    assert.match(chat, /removeEventListener\('scroll', onScroll, \{ capture: true \}\)/);
    assert.match(chat, /clearTimeout\(timer\)/);
});

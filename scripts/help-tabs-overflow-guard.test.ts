import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const help = readFileSync('components/help/HelpTabs.tsx', 'utf8');

test('F302: la barra de tabs de /help envuelve en pantallas estrechas', () => {
    // Medida QA: 413.25px de tabs en un viewport de 390px, sin wrap ni
    // scroller. flex-wrap garantiza que ningún tab queda fuera.
    assert.match(help, /flex flex-wrap gap-2 mb-8 border-b border-gray-700/);
});

test('F302: padding compacto en móvil, generoso desde sm', () => {
    const matches = help.match(/px-4 py-3 font-medium transition-colors sm:px-6/g) ?? [];
    assert.equal(matches.length, 3, 'los tres tabs llevan px-4 sm:px-6');
});

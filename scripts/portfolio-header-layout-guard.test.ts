import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const tabs = readFileSync('components/portfolio/PortfolioTabs.tsx', 'utf8');

test('F280: el header de /portfolio apila título y acciones hasta lg', () => {
    // A 768px (md) la fila sm:flex-row repartía el ancho entre el bloque del
    // título (min-w-0) y los 4 controles, y «Mi Cartera» se partía en dos
    // líneas. Hasta lg el header va en columna: título completo y acciones
    // debajo a todo el ancho.
    assert.match(tabs, /flex flex-col gap-4 mb-6 lg:flex-row lg:items-center lg:justify-between/);
    assert.doesNotMatch(tabs, /gap-4 mb-6 sm:flex-row/);
});

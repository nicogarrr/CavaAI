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

const summary = readFileSync('components/portfolio/PortfolioSummary.tsx', 'utf8');

test('F328: los importes del resumen se escalan a 360px en vez de recortarse', () => {
    // La grid-cols-2 a 360px deja cada tarjeta en ~164px y overflow-hidden
    // recortaba el importe (~21.5px): text-base -> text-lg -> text-2xl.
    const escalados = summary.match(/text-base min-\[420px\]:text-lg sm:text-2xl font-bold/g) ?? [];
    assert.equal(escalados.length, 4);
    assert.doesNotMatch(summary, /text-xl sm:text-2xl font-bold/);
});

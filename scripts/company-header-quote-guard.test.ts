/**
 * Quick win UX 1: la cabecera de la ficha muestra precio + variación % +
 * sparkline en todas las vistas (desktop y móvil), con degradación honesta
 * (proveedor caído -> bloque omitido, nunca un precio fabricado).
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { sparklinePoints } from '../lib/sparkline.ts';

const page = readFileSync('app/(root)/research/[ticker]/page.tsx', 'utf8');
const component = readFileSync('components/research/CompanyHeaderQuote.tsx', 'utf8');

test('el sparkline normaliza al viewBox y exige al menos dos cierres', () => {
    assert.equal(sparklinePoints([]), '');
    assert.equal(sparklinePoints([10]), '');
    const points = sparklinePoints([10, 15, 20]);
    const coords = points.split(' ').map((pair) => pair.split(',').map(Number));
    assert.deepEqual(coords[0], [0, 36]); // el mínimo abajo a la izquierda
    assert.deepEqual(coords[2], [120, 0]); // el máximo arriba a la derecha
    // Serie plana (span 0) no divide por cero ni rompe.
    assert.ok(sparklinePoints([7, 7, 7]).length > 0);
});

test('la cabecera compone la cotización en todas las vistas', () => {
    assert.match(page, /CompanyHeaderQuote snapshot=\{headerMarket\}/);
    // market ya no se lanza solo en overview: la cabecera lo usa siempre.
    assert.ok(
        !/activeView === 'overview' \? getCompanyMarketSnapshot/.test(page),
        'market sigue limitado a overview: la cabecera quedaría vacía en el resto de vistas',
    );
    // degradación honesta: el fallo del proveedor degrada a null, no a precio inventado.
    assert.match(page, /catch \{\s*headerMarket = null;\s*\}/);
});

test('el componente omite lo ausente y etiqueta el gráfico', () => {
    assert.match(component, /if \(quote\.price == null && history\.length === 0\) return null/);
    assert.match(component, /aria-label=\{`Evolución del precio/);
    assert.match(component, /sparklinePoints\(closes\)/);
    assert.match(component, /from '@\/lib\/sparkline'/);
});

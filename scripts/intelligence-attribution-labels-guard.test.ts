import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// @ts-expect-error TS5097
import { etiquetaComponenteAtribucion } from '../lib/labels.ts';

const page = readFileSync('app/(root)/portfolio/intelligence/page.tsx', 'utf8');

test('F282: el catálogo cerrado de componentes tiene etiqueta ES', () => {
    const esperadas: Record<string, string> = {
        fundamental_growth: 'Crecimiento fundamental',
        multiple: 'Múltiplo',
        dividends: 'Dividendos',
        buybacks: 'Recompras',
        dilution: 'Dilución',
        fx: 'Divisa',
        sizing: 'Tamaño de posición',
    };
    for (const [key, label] of Object.entries(esperadas)) {
        assert.equal(etiquetaComponenteAtribucion(key), label, key);
    }
});

test('F282: clave desconocida -> se muestra cruda, nunca oculta', () => {
    assert.equal(etiquetaComponenteAtribucion('nuevo_componente'), 'nuevo_componente');
});

test('F282: la cabecera de la tabla ya no pinta la clave cruda', () => {
    assert.match(page, /\{etiquetaComponenteAtribucion\(key\)\}/);
    assert.doesNotMatch(page, /key\.replaceAll\('_', ' '\)/);
});

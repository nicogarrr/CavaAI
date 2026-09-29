import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync('app/(root)/movers/page.tsx', 'utf8');

test('la pagina de movers muestra la frescura por fila y no vende una fecha global', () => {
    // Con el refresco a dos velocidades (tracked 1 h, universo 6 h) el
    // ranking mezcla series de distinta frescura. La cabecera no puede
    // decir "Datos del {as_of}" como si TODAS las filas fueran de ese dia:
    // as_of es el maximo y cada fila declara su propia fecha cuando difiere.
    assert.doesNotMatch(page, /Datos del \$\{movers\.as_of\}\./);
    assert.match(page, /row\.date && row\.date !== asOf/);
    assert.match(page, /del \{row\.date\}/);
    assert.match(page, /asOf=\{movers\.as_of\}/);
    assert.match(page, /su fecha aparece junto al precio/);
});

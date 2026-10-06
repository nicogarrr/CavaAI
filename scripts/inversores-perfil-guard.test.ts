/** Inversores sin 13F: la ficha publica muestra cada cifra con fuente, fecha y tipo; "Sin datos" solo por bloque. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const section = readFileSync('app/(root)/inversores/_components/PublicProfile.tsx', 'utf8');
const ficha = readFileSync('app/(root)/inversores/[slug]/page.tsx', 'utf8');
const actions = readFileSync('lib/actions/investors.actions.ts', 'utf8');

test('el tipo de hecho exige fuente, fecha y tipo', () => {
    assert.match(actions, /as_of: string;\s+source_url: string;\s+kind: 'oficial' \| 'inferido';/);
});

test('cada cifra se muestra con tipo, fecha y enlace a la fuente', () => {
    assert.match(section, /fact\.kind === 'oficial'/);
    assert.match(section, /fact\.as_of/);
    assert.match(section, /href=\{fact\.source_url\}/);
});

test('la cartera sin datos explica el motivo', () => {
    assert.match(section, /profile\.holdings_note/);
});

test('la ficha usa el perfil publico y conserva "Sin datos" cuando no hay', () => {
    assert.match(ficha, /investor\.public_profile \?/);
    assert.match(ficha, /<PublicProfileSection profile=\{investor\.public_profile\} \/>/);
    assert.match(ficha, /Sin datos: no presenta 13F/);
});

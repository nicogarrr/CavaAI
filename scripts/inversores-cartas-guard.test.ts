import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { authorKey, groupLetters, titleYear, type LetterDoc } from '../app/(root)/inversores/cartas/letters.ts';

const doc = (id: number, title: string, author: string | null, extra: Partial<LetterDoc> = {}): LetterDoc => ({
    id,
    title,
    author,
    document_type: 'fund_letter',
    source_url: `https://example.com/${id}.pdf`,
    publication_date: null,
    status: 'ready',
    ...extra,
});

test('el año sale del título y solo es una pista', () => {
    assert.equal(titleYear('Berkshire Hathaway - Carta anual accionistas 1977'), 1977);
    assert.equal(titleYear('Azvalor - carta a inversores 1s2023'), 2023);
    assert.equal(titleYear('Numantia Patrimonio - Carta ago2018'), 2018);
    assert.equal(titleYear('Carta sin año'), null);
});

test('agrupa por autor, solo cartas listas, más reciente primero y sin inventar fechas', () => {
    const groups = groupLetters([
        doc(1, 'Berkshire - Carta 1977', 'Warren Buffett'),
        doc(2, 'Berkshire - Carta 2023', 'Warren Buffett'),
        doc(3, 'Magallanes - Carta 1T26', 'Magallanes Value Investors'),
        doc(4, 'Tesis ASTS', 'Alguien', { document_type: 'third_party_thesis' }),
        doc(5, 'Carta rota 2020', 'Warren Buffett', { status: 'failed' }),
        doc(6, 'Carta anónima 2019', null),
    ]);
    assert.deepEqual(groups.map((g) => g.name), ['Warren Buffett', 'Magallanes Value Investors', 'Sin autor']);
    assert.deepEqual(groups[0].letters.map((l) => l.id), [2, 1]);
    assert.ok(groups.every((g) => g.letters.every((l) => l.publication_date === null)));
    assert.equal(authorKey('Emérito Quintana (Numantia Patrimonio)'), 'emerito-quintana-numantia-patrimonio');
});

test('la página dice "no registrada" sin fecha y enlaza lector y PDF original', () => {
    const page = readFileSync('app/(root)/inversores/cartas/page.tsx', 'utf8');
    assert.match(page, /Fecha de publicación no registrada/);
    assert.match(page, /\/knowledge\?document=\$\{letter\.id\}/);
    assert.match(page, /PDF original/);
    assert.match(page, /<Pagination/);
    assert.ok(!/IntersectionObserver|infinite/i.test(page), 'paginación, no scroll infinito');
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { resolveVisitBaseline, type StorageLike } from '../lib/research/visit-baseline.ts';

const mem = (): StorageLike & { data: Record<string, string> } => {
    const data: Record<string, string> = {};
    return { data, getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = v; } };
};

test('primera visita: sin referencia (no se inventa diff) y se registra la visita', () => {
    const local = mem(); const session = mem();
    assert.equal(resolveVisitBaseline(local, session, 'aapl', new Date('2026-10-13T10:00:00Z')), null);
    assert.equal(local.data['cavaai:last-visit:AAPL'], '2026-10-13T10:00:00.000Z');
});

test('segunda visita: compara con la anterior y recargar no borra la referencia', () => {
    const local = mem();
    resolveVisitBaseline(local, mem(), 'AAPL', new Date('2026-10-13T10:00:00Z'));
    const session = mem();
    const first = resolveVisitBaseline(local, session, 'AAPL', new Date('2026-10-14T09:00:00Z'));
    assert.equal(first, '2026-10-13T10:00:00.000Z');
    const reload = resolveVisitBaseline(local, session, 'AAPL', new Date('2026-10-14T09:05:00Z'));
    assert.equal(reload, '2026-10-13T10:00:00.000Z');
});

test('un valor corrupto en localStorage se ignora; cada empresa tiene su referencia', () => {
    const local = mem();
    local.setItem('cavaai:last-visit:MSFT', 'basura');
    assert.equal(resolveVisitBaseline(local, mem(), 'MSFT', new Date('2026-10-13T10:00:00Z')), null);
    assert.equal(local.getItem('cavaai:last-visit:AAPL'), null);
});

test('el banner solo enlaza https y la pagina lo monta', () => {
    const cmp = readFileSync('components/research/ChangesSinceVisit.tsx', 'utf8');
    assert.match(cmp, /\^https:/);
    assert.match(cmp, /rel="noopener noreferrer"/);
    const page = readFileSync('app/(root)/research/[ticker]/page.tsx', 'utf8');
    assert.match(page, /<ChangesSinceVisit ticker=\{ticker\} \/>/);
});

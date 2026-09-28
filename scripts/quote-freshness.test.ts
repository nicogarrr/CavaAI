import assert from 'node:assert/strict';
import test from 'node:test';
// @ts-expect-error -- node --test (--experimental-strip-types) exige la extension .ts
// en runtime; tsc la prohibe (TS5097). El supresor vive solo en este test.
import { classifyQuoteKind, sessionDateEt } from '../lib/market/quote-freshness.ts';

// F358: pruebas de comportamiento de la semantica de frescura de
// cotizaciones (sesion US, America/New_York, lun-vie 9:30-16:00).
const t = (iso: string) => Math.floor(new Date(iso).getTime() / 1000);
const now = (iso: string) => new Date(iso).getTime();

test('sesion en curso: cotizacion de hace minutos es live', () => {
    // Miercoles 30-sep-2026 15:00 UTC = 11:00 ET, mercado abierto.
    assert.equal(classifyQuoteKind(t('2026-09-30T14:50:00Z'), now('2026-09-30T15:00:00Z')), 'live');
});

test('F358: cache de AYER servida durante la sesion de hoy es stale (se rechaza)', () => {
    // Miercoles en sesion; t = martes 15:30 ET (caso BN: cierre previo como actual).
    assert.equal(classifyQuoteKind(t('2026-09-29T19:30:00Z'), now('2026-09-30T15:00:00Z')), 'stale');
});

test('finde NO rompe: cierre del viernes es close (ultimo cierre fechado), no stale', () => {
    const fridayClose = t('2026-10-02T20:00:00Z'); // viernes 16:00 ET
    assert.equal(classifyQuoteKind(fridayClose, now('2026-10-03T22:00:00Z')), 'close'); // sabado noche
    assert.equal(classifyQuoteKind(fridayClose, now('2026-10-04T15:00:00Z')), 'close'); // domingo
});

test('lunes pre-market: cierre del viernes sigue siendo close', () => {
    assert.equal(classifyQuoteKind(t('2026-10-02T20:00:00Z'), now('2026-10-05T12:00:00Z')), 'close'); // 08:00 ET
});

test('lunes EN sesion: cierre del viernes es stale (la cache 429 >24h no cuela)', () => {
    assert.equal(classifyQuoteKind(t('2026-10-02T20:00:00Z'), now('2026-10-05T15:00:00Z')), 'stale');
});

test('tras el cierre: la sesion de hoy es close fechado', () => {
    assert.equal(classifyQuoteKind(t('2026-10-02T19:30:00Z'), now('2026-10-02T21:00:00Z')), 'close');
});

test('timestamp roto o futuro es stale', () => {
    assert.equal(classifyQuoteKind(0, now('2026-09-30T15:00:00Z')), 'stale');
    assert.equal(classifyQuoteKind(t('2026-10-01T00:00:00Z'), now('2026-09-30T15:00:00Z')), 'stale');
});

test('sessionDateEt fecha el cierre en dia ET', () => {
    assert.equal(sessionDateEt(t('2026-10-02T20:00:00Z')), '2026-10-02');
});

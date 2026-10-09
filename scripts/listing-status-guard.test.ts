import assert from 'node:assert/strict';
import test from 'node:test';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { healthText, listingStatus } from '../lib/research/listing-status.ts';

const now = new Date('2026-10-09T12:00:00Z');

test('exchange UNKNOWN o cierre de hace más de 30 días => sin cotización vigente', () => {
  const stale = listingStatus('UNKNOWN', '2026-09-27', now);
  assert.deepEqual(stale, { stale: true, message: 'Ticker sin cotización vigente (último cierre 27/09/2026)' });
  assert.equal(listingStatus('NASDAQ', '2026-08-01', now).stale, true);
  assert.equal(listingStatus(null, null, now).stale, true);
});

test('un ticker vivo no se marca', () => {
  assert.deepEqual(listingStatus('NASDAQ', '2026-10-08', now), { stale: false });
  assert.deepEqual(listingStatus('NASDAQ', null, now), { stale: false });
});

test('la salud de un ticker caducado es Sin datos, nunca 0/100', () => {
  assert.equal(healthText(0, listingStatus('UNKNOWN', '2026-09-27', now)), 'Sin datos');
  assert.equal(healthText(null, { stale: false }), 'Sin datos');
  assert.equal(healthText(80, { stale: false }), '80/100');
});

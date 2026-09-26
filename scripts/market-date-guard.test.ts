/**
 * Guardas de fechas de mercado y de usuario (lib/format.ts).
 * Ejecución: node --experimental-strip-types --test scripts/market-date-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { formatMarketDate, formatUserDate, todayLocal } from '../lib/format.ts';

describe('fechas de mercado y de usuario', () => {
  it('un YYYY-MM-DD renderiza su dia literal, sin restar un dia por la zona del mercado', () => {
    // Bug: 'YYYY-MM-DD' se parseaba como medianoche local y se convertia a
    // America/New_York -> medianoche UTC/Madrid = tarde del DIA ANTERIOR en NY.
    assert.equal(formatMarketDate('2026-09-23'), '23 sept 2026');
    assert.equal(formatMarketDate('2026-01-01'), '1 ene 2026');
    assert.equal(formatUserDate('2026-09-23'), '23 sept 2026');
  });

  it('los instantes si se convierten a la zona del mercado', () => {
    // 01:00Z = 21:00 del dia anterior en Nueva York.
    assert.equal(formatMarketDate('2026-09-23T01:00:00Z'), '22 sept 2026');
    // 12:00Z = 08:00 en Nueva York, mismo dia.
    assert.equal(formatMarketDate('2026-09-23T12:00:00Z'), '23 sept 2026');
  });

  it('todayLocal da "hoy" en Europe/Madrid, no en la zona del proceso', () => {
    const esperado = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Europe/Madrid',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date());
    assert.match(todayLocal(), /^\d{4}-\d{2}-\d{2}$/);
    assert.equal(todayLocal(), esperado);
  });
});

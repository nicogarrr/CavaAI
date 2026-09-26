/**
 * F50: fechas+hora visibles siempre en Europe/Madrid fija. Con la zona
 * implícita, el SSR (UTC) y el navegador (local) imprimen textos distintos
 * cerca de medianoche y React rompe la hidratación (#418).
 * Ejecución: node --experimental-strip-types --test scripts/ssr-datetime-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { formatDateTime, formatUserDateTime } from '../lib/format.ts';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');

describe('F50: formato de fecha+hora estable entre SSR e hidratación', () => {
  // Instante a 5 minutos de medianoche en Madrid: en UTC ya es "mañana".
  const NEAR_MIDNIGHT = '2026-09-24T22:55:00.000Z';

  it('formatUserDateTime imprime lo mismo con TZ=UTC que con TZ=Europe/Madrid', () => {
    process.env.TZ = 'UTC';
    const ssr = formatUserDateTime(NEAR_MIDNIGHT);
    process.env.TZ = 'Europe/Madrid';
    const browser = formatUserDateTime(NEAR_MIDNIGHT);
    assert.equal(ssr, browser, 'el texto debe ser idéntico en servidor y navegador');
    assert.ok(ssr.includes('25'), '22:55Z son las 00:55 del 25 en Madrid');
  });

  it('formatDateTime (zona implícita) demuestra el bug que evita este guard', () => {
    process.env.TZ = 'UTC';
    const ssr = formatDateTime(NEAR_MIDNIGHT);
    process.env.TZ = 'Europe/Madrid';
    const browser = formatDateTime(NEAR_MIDNIGHT);
    assert.notEqual(ssr, browser, 'si esto fuera igual, el guard de arriba no protegería nada');
  });
});

describe('F50: ningún callsite visible usa ya la zona implícita', () => {
  const walk = (dir: string, out: string[] = []): string[] => {
    for (const entry of readdirSync(dir)) {
      if (entry === 'node_modules' || entry.startsWith('.')) continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full, out);
      else if (/\.(tsx|ts)$/.test(entry)) out.push(full);
    }
    return out;
  };

  it('app/ y components/ no llaman a formatDateTime', () => {
    const offenders: string[] = [];
    for (const scope of ['app', 'components']) {
      for (const file of walk(join(root, scope))) {
        const src = readFileSync(file, 'utf8');
        // llamadas reales, no la subcadena dentro de formatUserDateTime
        if (/[^A-Za-z]formatDateTime\(/.test(src)) offenders.push(file.slice(root.length + 1));
      }
    }
    assert.deepEqual(offenders, [], 'callsites con zona implícita: ' + offenders.join(', '));
  });
});

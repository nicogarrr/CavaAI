/**
 * Guarda del formato de mensajes de alerta: las cifras crudas persistidas
 * (Numeric(24, 6) sin formatear, p.ej. "200966000000.000000") se muestran
 * compactas en la tarjeta y la tarjeta usa el helper.
 * Ejecución: node --experimental-strip-types --test scripts/alerts-message-format-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { formatAlertMessageText } from '../lib/format.ts';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const source = (relativePath: string): string => readFileSync(join(root, relativePath), 'utf8');

describe('formatAlertMessageText', () => {
  it('compacta cifras crudas de 7+ dígitos con decimales', () => {
    assert.equal(
      formatAlertMessageText('RKLB revenue is 200966000000.000000 for FY2025.'),
      'RKLB revenue is 200,97 mil M for FY2025.',
    );
  });

  it('respeta cifras cortas y texto sin números', () => {
    assert.equal(formatAlertMessageText('sube 5,2 % y 12345 unidades'), 'sube 5,2 % y 12345 unidades');
    assert.equal(formatAlertMessageText('sin números'), 'sin números');
  });

  it('no inventa divisa: el resultado no lleva símbolo monetario', () => {
    const out = formatAlertMessageText('valor 416160000000');
    assert.equal(out, 'valor 416,16 mil M');
    assert.ok(!out.includes('€') && !out.includes('US$'));
  });
});

describe('la tarjeta de disparos aplica el formato', () => {
  it('AlertsManager formatea item.message con formatAlertMessageText', () => {
    const tsx = source('components/alerts/AlertsManager.tsx');
    assert.ok(
      tsx.includes('{formatAlertMessageText(item.message)}'),
      'la tarjeta de disparos debe formatear el mensaje',
    );
  });
});

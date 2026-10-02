/**
 * Guard: los pesos de categoria de las estrategias ProPicks son ratios (0-1, suman 1).
 * La ficha los mostraba todos como «0 %» por formatearlos como si fueran porcentajes.
 * Y la tarjeta de Telegram de Alertas no debe ensenar variables de entorno del servidor.
 *
 * Ejecutar: node --experimental-strip-types --test scripts/propicks-strategy-weights-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const factsheet = readFileSync('components/proPicks/StrategyFactsheet.tsx', 'utf8');
const strategies = readFileSync('lib/utils/proPicksStrategies.ts', 'utf8');
const alerts = readFileSync('components/alerts/AlertsManager.tsx', 'utf8');

describe('pesos de estrategia ProPicks', () => {
  it('la ficha formatea los pesos como ratio (sin fromRatio: false)', () => {
    assert.doesNotMatch(factsheet, /categoryWeights\[key\],\s*\{[^}]*fromRatio:\s*false/);
  });
  it('los pesos declarados son ratios <= 1', () => {
    const blocks = [...strategies.matchAll(/categoryWeights:\s*\{([^}]*)\}/g)];
    assert.ok(blocks.length >= 1);
    for (const [, body] of blocks) {
      const nums = [...body.matchAll(/:\s*([0-9.]+)/g)].map((m) => Number(m[1]));
      if (nums.length === 0) continue;
      assert.ok(nums.every((n) => n <= 1), `pesos fuera de ratio: ${body}`);
      assert.ok(Math.abs(nums.reduce((a, b) => a + b, 0) - 1) < 1e-6, `no suman 1: ${body}`);
    }
  });
});

describe('Alertas: aviso de Telegram', () => {
  it('no muestra variables de entorno del servidor al usuario', () => {
    assert.doesNotMatch(alerts, /TELEGRAM_(ENABLED|BOT_TOKEN|CHAT_ID)/);
  });
});

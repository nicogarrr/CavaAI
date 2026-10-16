/**
 * /calendar necesita un maxDuration por encima de su propio timeout de cliente.
 *
 * Bug observado en produccion (16 oct 2026, cuenta QA "Instinct Audit"):
 * /calendar devolvia 504 FUNCTION_INVOCATION_TIMEOUT a los ~10,4 s, de forma
 * reproducible. La causa es estructural, no un pico:
 *
 *  - vercel.json limita las paginas genericas a 10 s (entrada comodin de page.tsx);
 *  - la pagina llama a getCatalystCalendar() -> researchRequest('/api/calendar/catalysts'),
 *    cuyo presupuesto es RESEARCH_TIMEOUTS.GLOBAL_MS = 15 s (lib/research/client.ts);
 *  - el endpoint del backend tarda mas de 10 s en responder.
 *
 * Vercel mata la funcion a los 10 s, antes de que el timeout del cliente
 * (15 s) pueda disparar el camino disenado: AppError EXTERNAL_API_ERROR ->
 * isBackendUnavailableError -> <BackendOffline>. En lugar de una degradacion
 * honesta, el usuario ve un 504 crudo de plataforma.
 *
 * El fix declara `app/(root)/calendar/**` con maxDuration 30: holgura sobre
 * los 15 s del cliente para que sea el cliente quien agote su presupuesto y
 * la pagina degrade como esta disenado. Este guard impide que la entrada
 * desaparezca o quede por debajo del presupuesto del cliente.
 *
 * No sube el tope generico de 10 s de las paginas: solo esta pagina tiene
 * evidencia de superar los 10 s. Si otra pagina 504a, se mide y se declara
 * su propia entrada con la misma regla.
 *
 * Ejecucion: node --experimental-strip-types --test scripts/calendar-vercel-budget-guard.test.ts
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const VERCEL = JSON.parse(readFileSync('vercel.json', 'utf8')) as {
  functions: Record<string, { maxDuration?: number }>;
};

const CLIENT = readFileSync('lib/research/client.ts', 'utf8');
const GLOBAL_MS = Number(/GLOBAL_MS:\s*([\d_]+)/.exec(CLIENT)?.[1]?.replace(/_/g, ''));

test('GLOBAL_MS se lee de lib/research/client.ts', () => {
  assert.ok(Number.isFinite(GLOBAL_MS) && GLOBAL_MS > 0, 'no se pudo leer RESEARCH_TIMEOUTS.GLOBAL_MS');
});

test('app/(root)/calendar/** tiene maxDuration por encima del timeout del cliente', () => {
  const declared = VERCEL.functions['app/(root)/calendar/**']?.maxDuration;
  assert.ok(declared, 'falta la entrada app/(root)/calendar/** en vercel.json functions');
  assert.ok(
    declared * 1000 > GLOBAL_MS,
    `calendar maxDuration (${declared}s) debe superar el timeout del cliente (${GLOBAL_MS}ms) para que degrade con BackendOffline y no con un 504 crudo`,
  );
});

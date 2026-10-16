/**
 * /calendar necesita maxDuration por encima del peor caso real del cliente.
 *
 * Bug observado en produccion (16 oct 2026, cuenta QA "Instinct Audit"):
 * /calendar devolvia 504 FUNCTION_INVOCATION_TIMEOUT a los ~10,4 s, de forma
 * reproducible. La causa es estructural, no un pico:
 *
 *  - vercel.json limita las paginas genericas a 10 s;
 *  - la pagina llama a getCatalystCalendar() -> researchRequest('/api/calendar/catalysts'),
 *    cuyo presupuesto es RESEARCH_TIMEOUTS.GLOBAL_MS = 15 s (lib/research/client.ts);
 *  - el endpoint del backend tarda mas de 10 s en responder.
 *
 * Vercel mata la funcion a los 10 s, antes de que el timeout del cliente
 * pueda disparar el camino disenado: AppError EXTERNAL_API_ERROR ->
 * isBackendUnavailableError -> <BackendOffline>. En lugar de una degradacion
 * honesta, el usuario ve un 504 crudo de plataforma.
 *
 * Primera correccion (auditor NO FAVORABLE): subir solo maxDuration a 30 s
 * no cubria el peor caso real del cliente: un primer GET lento (~14,9 s)
 * que recibe 429 esperaba hasta 5 s y reintentaba con OTRA senal de 15 s
 * (~34,9 s total + auth/render). El retry tenia su propio presupuesto y
 * multiplicaba el de la pagina.
 *
 * Correccion definitiva, en dos piezas que este guard protege:
 *
 *  1. lib/research/client.ts: deadline UNICO por operacion. Cada intento
 *     recibe el tiempo que queda (remainingMs) y la espera del retry 429
 *     solo se hace si queda presupuesto para ella y para el reintento;
 *     si no, se devuelve el 429 tal cual. El peor caso vuelve a ser
 *     timeoutMs + overhead, no un multiplo.
 *  2. vercel.json: app/(root)/calendar/** con maxDuration 30, por encima
 *     de GLOBAL_MS (15 s) con margen para auth/render.
 *
 * No sube el tope generico de las paginas: solo esta ruta tiene evidencia
 * medida de superar los 10 s. Si otra pagina 504a, se mide y se declara
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

test('el retry 429 comparte un unico deadline por operacion', () => {
  assert.match(
    CLIENT,
    /const deadlineMs = Date\.now\(\) \+ timeoutMs;/,
    'researchRequest debe crear un deadline unico por operacion (sin el, el retry multiplica el peor caso)',
  );
  assert.match(
    CLIENT,
    /budgetLeftMs > waitMs \+ 250/,
    'la espera del retry 429 debe salir del mismo presupuesto y quedar acotada por el deadline',
  );
  assert.match(
    CLIENT,
    /signal: requestSignal\(requestInit\.signal, remainingMs\(\)\)/,
    'cada intento fetch debe usar el tiempo restante del deadline, no una senal nueva de timeoutMs',
  );
});

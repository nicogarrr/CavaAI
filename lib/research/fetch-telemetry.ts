/**
 * Telemetría por llamada de red de la ficha de research.
 *
 * Cada lectura (`/api/companies/{ticker}/snapshot`, el workspace de la vista,
 * el market, la watchlist...) deja un rastro con duración, resultado y motivo
 * del fallo. Sin esto, «la ficha tarda» es una impresión: no se sabe si el
 * coste está en el número de round-trips, en uno lento o en la degradación.
 *
 * Sin dependencias a propósito: el guard y los tests lo importan tal cual,
 * sin loader ni alias.
 */

/** Una lectura observada. `endpoint` es la ruta del backend, sin query. */
export type CallSample = {
  endpoint: string;
  /** Milisegundos que tardó la llamada (o el presupuesto si se abortó). */
  ms: number;
  ok: boolean;
  /** Código HTTP cuando lo hubo; undefined en fallo de transporte. */
  status?: number;
  /** Motivo del fallo: mensaje del error, timeout o cancelación. */
  reason?: string;
};

/** Muestra agregada por endpoint: lo que se usa para decidir y para volcar. */
export type EndpointSummary = {
  endpoint: string;
  calls: number;
  failures: number;
  totalMs: number;
  maxMs: number;
};

const MAX_SAMPLES = 200;

let samples: CallSample[] = [];
let verbose = false;

/** Activa el volcado por consola (desarrollo). Idempotente. */
export function enableResearchTelemetry(verboseMode = true): void {
  verbose = verboseMode;
}

/** Vacía la telemetría (tests, y entre navegaciones en desarrollo). */
export function resetResearchTelemetry(): void {
  samples = [];
}

/** Últimas muestras, en orden de llegada. */
export function researchTelemetry(): readonly CallSample[] {
  return samples;
}

/** Agregado por endpoint: nº de llamadas, fallos y coste. */
export function researchTelemetrySummary(): EndpointSummary[] {
  const byEndpoint = new Map<string, EndpointSummary>();
  for (const sample of samples) {
    const current = byEndpoint.get(sample.endpoint) ?? {
      endpoint: sample.endpoint,
      calls: 0,
      failures: 0,
      totalMs: 0,
      maxMs: 0,
    };
    current.calls += 1;
    if (!sample.ok) current.failures += 1;
    current.totalMs += sample.ms;
    current.maxMs = Math.max(current.maxMs, sample.ms);
    byEndpoint.set(sample.endpoint, current);
  }
  return [...byEndpoint.values()].sort((a, b) => b.totalMs - a.totalMs);
}

/**
 * Registra una llamada. `status` solo se sabe cuando hubo respuesta HTTP: un
 * fallo de red o un timeout no tienen código y se distinguen por `reason`.
 */
export function recordResearchCall(sample: CallSample): void {
  samples = [...samples, sample].slice(-MAX_SAMPLES);
  if (verbose) {
    const status = sample.ok ? `ok${sample.status ? ` ${sample.status}` : ''}` : `FAIL ${sample.reason ?? ''}`;
    console.log(`[research-telemetry] ${sample.endpoint} ${sample.ms}ms ${status}`);
  }
}

/**
 * Envuelve una lectura de red y registra su duración y su resultado.
 *
 * NO cambia el contrato: el error se propaga intacto para que quien llama
 * decida si degrada o tumba la página. Solo se mide.
 */
export async function withResearchTelemetry<T>(
  endpoint: string,
  run: () => Promise<T>,
): Promise<T> {
  const startedAt = performance.now();
  try {
    const value = await run();
    recordResearchCall({
      endpoint,
      ms: Math.round(performance.now() - startedAt),
      ok: true,
      status: 200,
    });
    return value;
  } catch (error) {
    recordResearchCall({
      endpoint,
      ms: Math.round(performance.now() - startedAt),
      ok: false,
      status: statusOf(error),
      reason: reasonOf(error),
    });
    throw error;
  }
}

function statusOf(error: unknown): number | undefined {
  if (typeof error !== 'object' || error === null) return undefined;
  const code = (error as { statusCode?: unknown }).statusCode;
  return typeof code === 'number' ? code : undefined;
}

function reasonOf(error: unknown): string {
  if (error instanceof DOMException && error.name === 'TimeoutError') return 'timeout';
  if (error instanceof DOMException && error.name === 'AbortError') return 'abort';
  if (typeof error === 'object' && error !== null) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === 'string' && message) return message;
  }
  return String(error);
}

/** Volca el agregado. Devuelve el texto para poder assertarlo en tests. */
export function dumpResearchTelemetry(): string {
  const summary = researchTelemetrySummary();
  if (!summary.length) return 'research-telemetry: sin muestras';
  const lines = summary.map((entry) =>
    `${entry.endpoint} calls=${entry.calls} failures=${entry.failures} total=${entry.totalMs}ms max=${entry.maxMs}ms`,
  );
  const text = `research-telemetry (${summary.length} endpoints)\n${lines.join('\n')}`;
  if (verbose) console.log(text);
  return text;
}
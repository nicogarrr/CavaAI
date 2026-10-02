/**
 * Agregacion de lecturas de la ficha de research.
 *
 * El problema que resuelve: la ficha era una cadena de `await` secuenciales
 * (snapshot -> market -> watchlist -> workspace de la vista). Con N llamadas y
 * latencia L el tiempo de pared era N x L, y nada de eso era dependencia de
 * datos: el watchlist no depende del snapshot, y el workspace de la vista se
 * pide por `ticker`, que ya se conoce antes de resolver el snapshot.
 *
 * Dos primitivas:
 *  - `launchResearchBatch`: lanza N lecturas a la vez y devuelve el lote. El
 *    reloj empieza AQUI, no al resolver: ese detalle es lo que hace que el
 *    presupuesto cubra el tiempo real ya consumido.
 *  - `settleResearchBatch`: las resuelve con `allSettled` (nunca `all`). Un 503
 *    de un widget lateral degrada a N/D con motivo en vez de tumbar la pagina.
 *
 * Sin dependencias a proposito: el guard y los tests lo importan tal cual,
 * sin loader ni alias.
 */

/**
 * Techo de la funcion en produccion: `vercel.json` declara
 * `"app/(root)/research/**": { "maxDuration": 60 }`. El guard falla si este
 * numero se desincroniza de ahi, asi que el presupuesto nunca es una constante
 * inventada.
 */
export const RESEARCH_RENDER_MAX_DURATION_MS = 60_000;

/**
 * Presupuesto que la pagina gasta en el lote de lecturas en paralelo.
 *
 * No es el techo: es lo que dejamos a la funcion. El resto (60s - 20s) es
 * margen para el render de React, el streaming de la respuesta y un pico de
 * latencia del borde. Medido: el lote completo son 2 fases de red (el snapshot
 * lanza a la vez el market, el watchlist y el workspace de la vista), asi que
 * 20s deja holgura incluso con el timeout corto del cliente (8s) encadenado
 * detras del global (15s).
 */
export const RESEARCH_RENDER_BUDGET_MS = 20_000;

/** Una lectura del lote. `run` recibe el signal del presupuesto. */
export type ResearchTask<T> = {
  /** Clave estable: es la etiqueta que sale en la telemetria y en los avisos. */
  key: string;
  run: (signal: AbortSignal) => Promise<T>;
};

/** Resultado de una lectura: o el valor, o el motivo por el que se degrado. */
export type ResearchSettled<T> =
  | { key: string; ok: true; value: T }
  | { key: string; ok: false; reason: string; error?: unknown };

/** Lote en vuelo: las promesas ya existen, solo falta recogerlas. */
export type ResearchBatch<T> = {
  /** Signal que aborta TODAS las lecturas del lote al agotarse el presupuesto. */
  signal: AbortSignal;
  /** Numero de lecturas lanzadas (diagnostico y tests). */
  size: number;
  settle: () => Promise<ResearchSettled<T>[]>;
};

/** Motivo legible de un fallo: timeout, cancelacion o mensaje del backend. */
export function researchFailureReason(error: unknown): string {
  if (error instanceof DOMException && error.name === 'TimeoutError') return 'timeout';
  if (error instanceof DOMException && error.name === 'AbortError') return 'abort';
  if (typeof error === 'object' && error !== null) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === 'string' && message) return message;
  }
  return String(error);
}

/**
 * Lanza las lecturas del lote de inmediato y devuelve el handle.
 *
 * Todas reciben el mismo `signal`: si alguien aborta (el presupuesto, o el
 * caller) ninguna se queda colgada sola. El drenaje de rechazos se adjunta en
 * CREACION porque un rechazo temprano, si el consumidor se engancha despues,
 * se convierte en `unhandledRejection` (mismo motivo que `drainRejection`).
 */
export function launchResearchBatch<T>(
  tasks: ResearchTask<T>[],
  budgetMs: number = RESEARCH_RENDER_BUDGET_MS,
): ResearchBatch<T> {
  const controller = new AbortController();
  // Sin unref a proposito (ver settleResearchBatch): el abort tiene que
  // dispararse aunque el resto del event loop este ocioso.
  const timer = setTimeout(
    () => controller.abort(new DOMException('presupuesto agotado', 'AbortError')),
    budgetMs,
  );
  const entries = tasks.map((task) => {
    const promise = task.run(controller.signal);
    // Drenaje EN CREACION: el lote puede quedarse sin recoger si el render se
    // corta antes (rama master-miss). `settle()` adjunta su propio manejador,
    // pero llega mas tarde, y un rechazo en esa ventana es un
    // `unhandledRejection` que tumba el proceso.
    void promise.catch(() => null);
    return { key: task.key, promise };
  });
  return {
    signal: controller.signal,
    size: entries.length,
    settle: async () => {
      try {
        return await settleResearchBatch(entries);
      } finally {
        clearTimeout(timer);
      }
    },
  };
}

/**
 * Resuelve el lote con `allSettled`: si K de N fallan, los N-K valores siguen
 * usables y los K degradan a N/D CON motivo. Nunca lanza.
 *
 * Un `Promise.all` naked convertia un 503 de un widget lateral en una pagina en
 * blanco; esto es exactamente lo que sustituye.
 */
export async function settleResearchBatch<T>(
  promises: Array<{ key: string; promise: Promise<T> }>,
  budgetMs: number = RESEARCH_RENDER_BUDGET_MS,
): Promise<ResearchSettled<T>[]> {
  // El presupuesto se aplica ENTRADA POR ENTRADA, no al lote entero: una
  // lectura lenta no puede tirar abajo una que ya ha respondido. Si una
  // colgada deploma tambien a la rapida, el "N-K valores se usan" es mentira.
  return Promise.all(
    promises.map(async (entry) => {
      // Sin unref a proposito: el temporizador del presupuesto TIENE que
      // dispararse. Con unref, un lote cuya unica lectura esta colgada deja
      // el event loop vacio y el presupuesto no llega a expirar nunca.
      let timer: ReturnType<typeof setTimeout> | undefined;
      const timeout = new Promise<'deadline'>((resolve) => {
        timer = setTimeout(() => resolve('deadline'), budgetMs);
      });
      try {
        const result = await Promise.race([
          entry.promise.then((value) => ({ ok: true, value }) as const),
          timeout,
        ]);
        // El presupuesto no CUELA la lectura: la degrada. Una que no llega a
        // tiempo vale lo mismo que una que falla, y asi la pagina se pinta.
        if (result === 'deadline') return { key: entry.key, ok: false, reason: 'timeout' };
        return { key: entry.key, ok: true, value: result.value };
      } catch (error) {
        return { key: entry.key, ok: false, reason: researchFailureReason(error), error };
      } finally {
        clearTimeout(timer);
      }
    }),
  );
}

/**
 * Valor de una entrada del lote, o `fallback` si fallo o no estaba.
 *
 * Es el punto donde "degradar a N/D" se hace explicito: la pagina llama a
 * `pick(...)` con el estado vacio honesto de cada panel, nunca con un valor
 * inventado. `reason` sale por separado para poder mostrarlo.
 */
export function pick<T>(
  settled: ResearchSettled<T>[],
  key: string,
  fallback: T,
): T {
  const found = settled.find((entry) => entry.key === key);
  if (!found || !found.ok) return fallback;
  return found.value;
}

/** Motivos de degradacion del lote, por clave. Para la aviso de la pagina. */
export function degradedReasons<T>(settled: ResearchSettled<T>[]): Array<{ key: string; reason: string }> {
  return settled
    .filter((entry): entry is { key: string; ok: false; reason: string } => !entry.ok)
    .map((entry) => ({ key: entry.key, reason: entry.reason }));
}
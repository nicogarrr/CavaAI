/**
 * Caché corta en memoria con TTL para server actions.
 *
 * Envuelve el singleton `requestCache` (deduplica concurrentes a la misma
 * clave) y añade limpieza oportunista de entradas expiradas, ya que en el
 * servidor no corre el `setInterval` de limpieza (solo existe en `window`).
 *
 * Uso: envolver lecturas idempotentes y frescas-por-segundos (índices,
 * quotes) sin cambiar su forma de retorno. Los misses (`null`/`undefined`)
 * no se cachean salvo `cacheNull: true`, para no fijar errores
 * transitorios durante todo el TTL.
 */

import { requestCache } from './requestCache';

let calls = 0;

export async function cachedFetch<T>(
  key: string,
  fetcher: () => Promise<T>,
  ttlSeconds: number,
  opts: { cacheNull?: boolean } = {},
): Promise<T> {
  // Limpieza oportunista cada 50 llamadas: evita crecimiento
  // ilimitado del Map en el proceso del servidor.
  if (++calls % 50 === 0) {
    requestCache.clearExpired(Math.max(ttlSeconds, 120));
  }
  const data = await requestCache.get(key, fetcher, ttlSeconds);
  if ((data === null || data === undefined) && opts.cacheNull !== true) {
    requestCache.invalidate(key);
  }
  return data;
}

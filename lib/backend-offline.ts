import { AppError } from '@/lib/types/errors';

/**
 * Detecta errores de "motor de análisis no disponible" (el backend FastAPI
 * está apagado o es inalcanzable desde Vercel).
 *
 * - ExternalAPIError: el fetch al backend ni siquiera respondió
 *   (ECONNREFUSED, DNS, timeout…).
 * - RESEARCH_API_ERROR con 5xx: el backend respondió pero está fallando
 *   (arrancando, dependencia caída…).
 *
 * Los 4xx (auth, validación, no encontrado) NO cuentan como backend caído:
 * deben seguir propagándose para no ocultar errores reales.
 */
export function isBackendUnavailableError(error: unknown): boolean {
  if (!(error instanceof AppError)) return false;
  if (error.code === 'EXTERNAL_API_ERROR') return true;
  return error.code === 'RESEARCH_API_ERROR' && error.statusCode >= 500;
}

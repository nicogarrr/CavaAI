/**
 * Validacion de segmentos de ruta antes de interpolarlos en un path del
 * research engine.
 *
 * Una anotacion de tipo (`fiscalYear: number`) no valida nada en runtime: una
 * Server Action recibe JSON arbitrario del cliente. `researchRequest` hace
 * `fetch(`${BACKEND_URL}${path}`)`, y fetch normaliza `..` antes de enviar, de
 * modo que un valor como `../../../openapi` acababa pidiendo `/openapi` en el
 * engine firmado: no solo cambia el endpoint, ademas la firma HMAC seguia
 * valiendo porque la firma se calcula sobre el path ya normalizado.
 */

import { ValidationError } from '@/lib/types/errors';

/** Identificador numerico de base de datos: entero positivo, sin signo ni notacion. */
export function assertPositiveInt(value: unknown, field: string): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new ValidationError(`${field} debe ser un entero positivo`, field);
  }
  return parsed;
}

/** Anio civil: entero en un rango que cubre historico y proyecciones. */
export function assertYear(value: unknown, field: string, min = 1900, max = 2200): number {
  const parsed = assertPositiveInt(value, field);
  if (parsed < min || parsed > max) {
    throw new ValidationError(`${field} debe estar entre ${min} y ${max}`, field);
  }
  return parsed;
}

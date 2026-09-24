/**
 * Helpers únicos de formateo para toda la app (es-ES).
 *
 * Toda cifra, fecha o importe visible en UI debe pasar por aquí: evita la
 * mezcla de formatos en-US/es-ES detectada en la auditoría de frontend y
 * garantiza separadores de miles/meses españoles en todos los viewports.
 */

export const FORMAT_LOCALE = 'es-ES';

/** Valor numérico tolerante (string de backend, null, undefined) */
export type NumericInput = number | string | null | undefined;

/** Placeholder unificado para valores ausentes */
export const NA = 'N/D';

function toFinite(value: NumericInput): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Parsea números escritos por el usuario tolerando el formato es-ES.
 * "12,53" -> 12.53, "1.234,56" -> 1234.56, "1234.56" -> 1234.56.
 * Regla: si hay coma se asume decimal español (los puntos son miles);
 * sin coma, se parsea tal cual. Entrada inválida -> null (nunca trunca
 * en silencio como parseFloat("12,53") -> 12).
 */
export function parseLocalizedNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const normalized = trimmed.includes(',')
    ? trimmed.replace(/\./g, '').replace(',', '.')
    : trimmed;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function toDate(value: string | number | Date | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * Número con separadores españoles (1.234,56).
 * Acepta `Intl.NumberFormatOptions` para decimales/notación.
 */
export function formatNumber(
  value: NumericInput,
  options: Intl.NumberFormatOptions = {},
  fallback: string = NA,
): string {
  const parsed = toFinite(value);
  if (parsed === null) return fallback;
  return new Intl.NumberFormat(FORMAT_LOCALE, {
    maximumFractionDigits: 2,
    ...options,
  }).format(parsed);
}

/**
 * Importe monetario con locale es-ES (1.234,56 US$ / 1.234,56 €).
 */
export function formatMoney(
  value: NumericInput,
  currency = 'USD',
  options: Intl.NumberFormatOptions = {},
  fallback: string = NA,
): string {
  const parsed = toFinite(value);
  if (parsed === null) return fallback;
  return new Intl.NumberFormat(FORMAT_LOCALE, {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
    ...options,
  }).format(parsed);
}

/**
 * Cifra compacta en español (1,2 M · 3,4 mil M) para métricas y market caps.
 */
export function formatCompact(
  value: NumericInput,
  options: Intl.NumberFormatOptions = {},
  fallback: string = NA,
): string {
  const parsed = toFinite(value);
  if (parsed === null) return fallback;
  return new Intl.NumberFormat(FORMAT_LOCALE, {
    notation: 'compact',
    maximumFractionDigits: 2,
    ...options,
  }).format(parsed);
}

/**
 * Porcentaje en español. Por defecto `value` es ratio (0.15 -> 15,0 %);
 * con `fromRatio: false` ya viene en tanto por ciento (15 -> 15,0 %).
 */
export function formatPercent(
  value: NumericInput,
  { fromRatio = true, digits = 1, signDisplay }: { fromRatio?: boolean; digits?: number; signDisplay?: 'auto' | 'always' | 'never' } = {},
  fallback: string = NA,
): string {
  const parsed = toFinite(value);
  if (parsed === null) return fallback;
  const ratio = fromRatio ? parsed : parsed / 100;
  return new Intl.NumberFormat(FORMAT_LOCALE, {
    style: 'percent',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    ...(signDisplay ? { signDisplay } : {}),
  }).format(ratio);
}

/**
 * Fecha corta en español (23 sept 2026). Acepta Date, ISO o timestamp.
 */
export function formatDate(
  value: string | number | Date | null | undefined,
  options: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' },
  fallback: string = NA,
): string {
  const date = toDate(value);
  if (!date) return fallback;
  return new Intl.DateTimeFormat(FORMAT_LOCALE, options).format(date);
}

/**
 * Fecha + hora en español (23 sept 2026, 18:30).
 */
export function formatDateTime(
  value: string | number | Date | null | undefined,
  options: Intl.DateTimeFormatOptions = {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  },
  fallback: string = NA,
): string {
  return formatDate(value, options, fallback);
}

/**
 * Tiempo relativo en español ("hace 3 días", "hace 12 minutos").
 * `timestamp` viene en segundos (formato de APIs de noticias).
 */
export function formatTimeAgo(timestamp: number | string | Date | null | undefined): string {
  const date =
    timestamp instanceof Date || typeof timestamp === 'string'
      ? toDate(timestamp)
      : toFinite(timestamp) !== null
        ? new Date(toFinite(timestamp)! * 1000)
        : null;
  if (!date) return NA;
  const diffInMs = Date.now() - date.getTime();
  const diffInMinutes = Math.max(0, Math.floor(diffInMs / (1000 * 60)));
  const diffInHours = Math.floor(diffInMinutes / 60);
  const diffInDays = Math.floor(diffInHours / 24);
  if (diffInDays > 0) return `hace ${diffInDays} ${diffInDays === 1 ? 'día' : 'días'}`;
  if (diffInHours >= 1) return `hace ${diffInHours} ${diffInHours === 1 ? 'hora' : 'horas'}`;
  return `hace ${diffInMinutes} ${diffInMinutes === 1 ? 'minuto' : 'minutos'}`;
}


/**
 * El backend serializa los Numeric monetarios como string|null (nunca
 * asumir string): convierte a number con fallback cuando falta el dato
 * o llega malformado. Vive aquí (módulo puro) porque las server actions
 * no pueden exportar funciones síncronas.
 */
export function researchMoneyToNumber(
  value: string | null | undefined,
  fallback = 0,
): number {
  if (value === null || value === undefined || value === '') return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

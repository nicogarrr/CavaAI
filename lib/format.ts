/**
 * Helpers únicos de formateo para toda la app (es-ES).
 *
 * Toda cifra, fecha o importe visible en UI debe pasar por aquí: evita la
 * mezcla de formatos en-US/es-ES detectada en la auditoría de frontend y
 * garantiza separadores de miles/meses españoles en todos los viewports.
 */

export const FORMAT_LOCALE = 'es-ES';

/** Zona del mercado de referencia: cierres, velas y datos de cotizaciones. */
export const MARKET_TZ = 'America/New_York';

/** Zona del usuario: todo lo que es "su" fecha (suscripción, tenencias, CFD). */
export const USER_TZ = 'Europe/Madrid';

/** Valor numérico tolerante (string de backend, null, undefined) */
export type NumericInput = number | string | null | undefined;

/** Placeholder unificado para valores ausentes */
export const NA = 'N/D';

/**
 * Placeholder unificado para ESTADOS DE FLUJO: la tesis aún no se ha
 * generado, el job está en cola, la promesa no se ha conciliado.
 *
 * Por qué NO reutilizamos `NA` aunque los dos mean "no hay valor": `NA` dice
 * que el dato NO EXISTE o no se pudo traer y siempre arrastra un CTA de
 * reintento; `NO_CORRIDO` dice que el dato AÚN NO SE HA CALCULADO y no
 * lleva acción posible. Un token común impediría al usuario —y a soporte—
 * distinguir "CavaAI está roto" de "todavía no lo has pedido".
 */
export const NO_CORRIDO = 'No corrido';

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
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  // "YYYY-MM-DD" es UTC midnight para `new Date(string)`: en un TZ negativo se
  // ve el día anterior. Se parsea como fecha local explícita (día del ledger,
  // fecha de transacción, vencimiento de CFD: son días de calendario, no
  // instantes). Cualquier otra cadena (ISO con hora, etc.) sí es un instante.
  const dateOnly = typeof value === 'string' ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(value) : null;
  const date = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(value);
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
 * Precio con decimales dinámicos: los valores muy pequeños (microcaps,
 * abs < 0,01) necesitan más de 2 decimales para no salir como "0,00 US$"
 * cuando el precio real es distinto de cero (F35, SANW 0,0011 US$).
 * Por debajo de 0,01 se usan dígitos significativos en vez de decimales fijos.
 */
export function formatPrice(
  value: NumericInput,
  currency = 'USD',
  options: Intl.NumberFormatOptions = {},
  fallback: string = NA,
): string {
  const parsed = toFinite(value);
  if (parsed === null) return fallback;
  const small = parsed !== 0 && Math.abs(parsed) < 0.01;
  return new Intl.NumberFormat(FORMAT_LOCALE, {
    style: 'currency',
    currency,
    ...(small
      ? { maximumSignificantDigits: 4 }
      : { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    ...options,
  }).format(parsed);
}

/**
 * Cifra compacta en español (1,2 M · 3,4 mil M) para métricas y market caps.
 *
 * Intl es-ES con notation "compact" es inconsistente para miles de millones:
 * 9.447.000.000 se renderiza como "9447 M" mientras que 416.160.000.000 sale
 * como "416,16 mil M" (B18). Aquí la escala se fija siempre: millones como
 * "M" y miles de millones como "mil M", con decimales es-ES.
 */
export function formatCompact(
  value: NumericInput,
  options: Intl.NumberFormatOptions = {},
  fallback: string = NA,
): string {
  const parsed = toFinite(value);
  if (parsed === null) return fallback;
  const abs = Math.abs(parsed);
  const { maximumFractionDigits = 2, ...rest } = options;
  if (abs >= 1e9) {
    return `${formatNumber(parsed / 1e9, { maximumFractionDigits, ...rest }, fallback)} mil M`;
  }
  if (abs >= 1e6) {
    return `${formatNumber(parsed / 1e6, { maximumFractionDigits, ...rest }, fallback)} M`;
  }
  return new Intl.NumberFormat(FORMAT_LOCALE, {
    notation: 'compact',
    maximumFractionDigits,
    ...rest,
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
 * Sin `timeZone` por defecto: el comportamiento actual no cambia para los
 * call sites existentes; para fechas con zona definida usa `formatUserDate`
 * o `formatMarketDate`.
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
 * Fecha en la zona del mercado (cierre de una vela, fecha de cotización).
 */
export function formatMarketDate(
  value: string | number | Date | null | undefined,
  options: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' },
  fallback: string = NA,
): string {
  return formatDate(value, { ...options, timeZone: MARKET_TZ }, fallback);
}

/**
 * Fecha en la zona del usuario (fechas de calendario propias).
 */
export function formatUserDate(
  value: string | number | Date | null | undefined,
  options: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' },
  fallback: string = NA,
): string {
  return formatDate(value, { ...options, timeZone: USER_TZ }, fallback);
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

/** Fecha + hora en la zona del mercado (hora de cierre de sesión). */
export function formatMarketDateTime(
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
  return formatDate(value, { ...options, timeZone: MARKET_TZ }, fallback);
}

/** Fecha + hora en la zona del usuario. */
/**
 * Etiqueta de fecha "generada el ..." para tesis y memos.
 *
 * Un timestamp PRESENTE pero invalido no debe caer en el fallback `NA`:
 * pintar "generada el N/D" enmascara un dato roto como si el dato
 * faltara. Guard explicito: fecha ausente o no parseable devuelve null
 * (la UI omite la etiqueta), solo una fecha valida se formatea.
 */
export function formatGeneratedDate(
  value: string | number | Date | null | undefined,
  options: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' },
): string | null {
  if (value === null || value === undefined) return null;
  const parsed = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return formatUserDate(parsed, options);
}

export function formatUserDateTime(
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
  return formatDate(value, { ...options, timeZone: USER_TZ }, fallback);
}

/**
 * "Hoy" del usuario en `YYYY-MM-DD`, listo para `<input type="date">`.
 *
 * `new Date().toISOString().split('T')[0]` devuelve el día en UTC: entre las
 * 22:00 y las 00:00 Europe/Madrid el servidor (UTC) da el día de mañana y el
 * navegador da el de hoy, así que el default del input difiere entre el HTML
 * del servidor y la hidratación.
 */
export function todayLocal(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Tiempo relativo en español ("hace 3 días", "hace 12 minutos").
 * `timestamp` viene en segundos (formato de APIs de noticias).
 *
 * `now` permite pasar el instante de referencia calculado en el servidor: sin
 * él, `Date.now()` dentro del render rompe la hidratación en client
 * components (el servidor y el navegador pueden caer en buckets distintos).
 */
export function formatTimeAgo(
  timestamp: number | string | Date | null | undefined,
  now: number | Date = Date.now(),
): string {
  const date =
    timestamp instanceof Date || typeof timestamp === 'string'
      ? toDate(timestamp)
      : toFinite(timestamp) !== null
        ? new Date(toFinite(timestamp)! * 1000)
        : null;
  if (!date) return NA;
  const reference = now instanceof Date ? now.getTime() : now;
  const diffInMs = reference - date.getTime();
  const diffInMinutes = Math.max(0, Math.floor(diffInMs / (1000 * 60)));
  const diffInHours = Math.floor(diffInMinutes / 60);
  const diffInDays = Math.floor(diffInHours / 24);
  if (diffInDays > 0) return `hace ${diffInDays} ${diffInDays === 1 ? 'día' : 'días'}`;
  if (diffInHours >= 1) return `hace ${diffInHours} ${diffInHours === 1 ? 'hora' : 'horas'}`;
  if (diffInMinutes >= 1) {
    return `hace ${diffInMinutes} ${diffInMinutes === 1 ? 'minuto' : 'minutos'}`;
  }
  return 'ahora mismo';
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

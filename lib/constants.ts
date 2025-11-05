/**
 * Constantes centralizadas del proyecto
 * Reemplaza magic numbers y strings hardcodeados
 */

// Timeouts (en milisegundos)
export const TIMEOUTS = {
  API_REQUEST: 10000, // 10 segundos para requests de API
  API_REQUEST_FAST: 8000, // 8 segundos para requests rápidos
  DATABASE_CONNECTION: 30000, // 30 segundos para conexión a DB
  SERVER_SELECTION: 30000, // 30 segundos para selección de servidor MongoDB
} as const;

// Cache TTL (en segundos)
export const CACHE_TTL = {
  REALTIME_DATA: 60, // Datos en tiempo real (precios, noticias)
  SEMI_STATIC_DATA: 3600, // Datos semi-estáticos (perfiles, métricas)
  STATIC_DATA: 21600, // Datos estáticos (info de empresa) - 6 horas
} as const;

// Rate limits
export const RATE_LIMITS = {
  API_ROUTE: {
    window: '1 m', // 1 minuto
    limit: 60, // 60 requests por ventana
  },
  QUOTE_API: {
    window: '1 m',
    limit: 30, // 30 requests por minuto para quotes
  },
} as const;

// Validación de símbolos
export const SYMBOL_VALIDATION = {
  MIN_LENGTH: 1,
  MAX_LENGTH: 10,
  PATTERN: /^[A-Z0-9.-]+$/, // Solo letras mayúsculas, números, puntos y guiones
} as const;

// Headers de seguridad
export const SECURITY_HEADERS = {
  'X-DNS-Prefetch-Control': 'on',
  'X-Frame-Options': 'SAMEORIGIN',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
} as const;

// Configuración de logging
export const LOG_LEVELS = {
  ERROR: 'error',
  WARN: 'warn',
  INFO: 'info',
  DEBUG: 'debug',
} as const;

// Mensajes de error comunes
export const ERROR_MESSAGES = {
  AUTH_FAILED: 'Authentication failed. Please check your credentials.',
  AUTH_UNAVAILABLE: 'Authentication service is temporarily unavailable. Please try again later.',
  INVALID_SYMBOL: 'Invalid symbol format. Symbols must be 1-10 characters and contain only letters, numbers, dots, and hyphens.',
  MISSING_API_KEY: 'API key not configured. Please check your environment variables.',
  RATE_LIMIT_EXCEEDED: 'Rate limit exceeded. Please try again later.',
  DATABASE_ERROR: 'Database connection failed. Please try again later.',
  EXTERNAL_API_ERROR: 'Failed to fetch data from external service.',
  NOT_FOUND: 'Resource not found.',
  VALIDATION_ERROR: 'Invalid input data.',
} as const;

export const NAV_ITEMS = [
  { href: '/', label: 'Home' },
  { href: '/funds/rankings', label: 'Rankings' },
  { href: '/propicks', label: 'Pro Picks' },
  // Screener eliminado
] as const;

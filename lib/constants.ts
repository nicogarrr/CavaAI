/**
 * Constantes centralizadas del proyecto
 * Reemplaza magic numbers y strings hardcodeados
 */

import {
  Bell,
  BookOpen,
  Briefcase,
  Building2,
  Filter,
  Gauge,
  Home,
  Receipt,
  Sparkles,
  Star,
  Target,
  TrendingUp,
  Landmark,
    Users,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

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
  'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
  'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https:; frame-ancestors 'self'; base-uri 'self'; form-action 'self'",
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

// Etiquetas en espanol, alineadas con el titulo (H1) de cada pagina.
// Menu agrupado por secciones (aprobado por Nico 2026-09-23, revisado
// 2026-09-25): Cartera es un árbol (cartera + exposiciones + intelligence),
// Análisis no duplica Inicio, Movers/Insider/13F son señales accionables,
// Corp. es conciliación de cartera y Exportar vive en cada objeto.
// "Buscar" vive fijo en la cabecera (Ctrl+K) y "Seguridad" en el menu del
// avatar, asi que no se repiten aqui; /search y /security siguen existiendo.
export const NAV_SECTIONS = [
  {
    title: 'Principal',
    items: [
      { href: '/', label: 'Inicio', icon: Home },
      { href: '/portfolio', label: 'Cartera', icon: Briefcase },
      { href: '/portfolio/intelligence', label: 'Cartera · Inteligencia', icon: Sparkles },
      { href: '/risk', label: 'Cartera · Exposiciones', icon: Gauge },
      { href: '/propicks', label: 'ProPicks', icon: Sparkles },
    ],
  },
  {
    title: 'Señales',
    items: [
      { href: '/watchlist', label: 'Watchlist', icon: Star },
      { href: '/movers', label: 'Señales · Movers', icon: TrendingUp },
      { href: '/insider', label: 'Señales · Insider', icon: Users },
      { href: '/ownership', label: 'Señales · 13F', icon: Landmark },
      { href: '/alerts', label: 'Alertas', icon: Bell },
      { href: '/screeners', label: 'Screeners', icon: Filter },
    ],
  },
  {
    title: 'Mi plan',
    items: [
      { href: '/plan', label: 'Plan', icon: Target },
      { href: '/taxes', label: 'Impuestos', icon: Receipt },
      { href: '/corporate-actions', label: 'Cartera · Acciones corp.', icon: Building2 },
    ],
  },
  {
    title: 'Sistema',
    items: [
      { href: '/knowledge', label: 'Conocimiento', icon: BookOpen },
    ],
  },
];

// Lista plana derivada, por compatibilidad con consumidores existentes.
export const NAV_ITEMS: ReadonlyArray<{ href: string; label: string; icon: LucideIcon }> =
  NAV_SECTIONS.reduce<Array<{ href: string; label: string; icon: LucideIcon }>>(
    (acc, section) => acc.concat(section.items),
    [],
  );

// TradingView eliminado (P1): 0 usos verificados. Reintroducir bajo feature flag si vuelve.
export const MARKET_DATA_WIDGET_CONFIG = {
  colorTheme: "dark",
  width: "100%",
  height: 46,
  showFloatingTooltip: true,
  symbolType: "stock",
  locale: "es",
  isTransparent: true,
  largeChartUrl: "",
  showSymbolLogo: true,
  symbols: [
    { title: "S&P 500", proName: "FOREXCOM:SPXUSD" },
    { title: "Nasdaq 100", proName: "FOREXCOM:NSXUSD" },
    { title: "EUR/USD", proName: "FX_IDC:EURUSD" },
    { title: "BTC/USD", proName: "BITSTAMP:BTCUSD" },
    { title: "Gold", proName: "OANDA:XAUUSD" }
  ]
} as const;

export const MARKET_OVERVIEW_WIDGET_CONFIG = {
  colorTheme: "dark",
  width: "100%",
  height: 400,
  locale: "es",
  isTransparent: true,
  showSymbolLogo: true,
  dateRange: "12M",
  plotLineColorGrowing: "rgba(41, 98, 255, 1)",
  plotLineColorFalling: "rgba(255, 82, 82, 1)",
  gridLineColor: "rgba(42, 46, 57, 0)",
  scaleFontColor: "rgba(134, 137, 147, 1)",
  belowLineFillColorGrowing: "rgba(41, 98, 255, 0.12)",
  belowLineFillColorFalling: "rgba(255, 82, 82, 0.12)",
  tabs: [
    {
      title: "Índices",
      symbols: [
        { s: "FOREXCOM:SPXUSD", d: "S&P 500" },
        { s: "FOREXCOM:NSXUSD", d: "Nasdaq 100" },
        { s: "FOREXCOM:DJI", d: "Dow 30" },
        { s: "INDEX:IBEX35", d: "IBEX 35" }
      ]
    },
    {
      title: "Forex",
      symbols: [
        { s: "FX:EURUSD", d: "EUR/USD" },
        { s: "FX:GBPUSD", d: "GBP/USD" },
        { s: "FX:USDJPY", d: "USD/JPY" }
      ]
    },
    {
      title: "Criptos",
      symbols: [
        { s: "BITSTAMP:BTCUSD", d: "Bitcoin" },
        { s: "BITSTAMP:ETHUSD", d: "Ethereum" },
        { s: "BINANCE:SOLUSD", d: "Solana" }
      ]
    }
  ]
} as const;

export const NEWS_SYMBOLS = [
  "NASDAQ:AAPL",
  "NASDAQ:MSFT",
  "NASDAQ:GOOGL",
  "NASDAQ:AMZN",
  "NASDAQ:NVDA",
  "NASDAQ:META",
  "NASDAQ:TSLA",
  "NYSE:JPM",
  "NYSE:V",
  "NYSE:JNJ"
] as const;

export const POPULAR_STOCK_SYMBOLS = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
  "JPM", "V", "JNJ", "UNH", "HD", "PG", "MA", "DIS",
  "NFLX", "ADBE", "CRM", "AMD", "INTC", "PYPL", "COST",
  "PEP", "KO", "NKE", "MCD", "WMT", "BA", "GS", "UBER"
] as const;

// Onboarding options
export const INVESTMENT_GOALS = [
  { value: "growth", label: "Crecimiento a largo plazo" },
  { value: "income", label: "Ingresos por dividendos" },
  { value: "value", label: "Value Investing" },
  { value: "speculation", label: "Trading especulativo" },
  { value: "retirement", label: "Ahorro para jubilación" },
  { value: "education", label: "Aprender a invertir" }
] as const;

export const RISK_TOLERANCE_OPTIONS = [
  { value: "conservative", label: "Conservador - Mínimo riesgo" },
  { value: "moderate", label: "Moderado - Balance riesgo/retorno" },
  { value: "aggressive", label: "Agresivo - Alto riesgo, alto retorno" },
  { value: "very_aggressive", label: "Muy agresivo - Máximo potencial" }
] as const;

export const PREFERRED_INDUSTRIES = [
  { value: "technology", label: "Tecnología" },
  { value: "healthcare", label: "Salud" },
  { value: "finance", label: "Finanzas" },
  { value: "consumer", label: "Consumo" },
  { value: "energy", label: "Energía" },
  { value: "industrial", label: "Industrial" },
  { value: "real_estate", label: "Inmobiliario" },
  { value: "materials", label: "Materiales" },
  { value: "utilities", label: "Utilities" },
  { value: "communication", label: "Comunicación" }
] as const;

// Widgets TradingView eliminados (P1): ver nota arriba.

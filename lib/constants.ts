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

// TradingView Widget Configs
export const HEATMAP_WIDGET_CONFIG = {
  exchanges: [],
  dataSource: 'SPX500',
  grouping: 'no_group',
  blockSize: 'market_cap_custom',
  blockColor: 'change',
  locale: 'en',
  symbolUrl: '',
  colorTheme: 'dark',
  hasTopBar: false,
  isDataSetEnabled: false,
  isZoomEnabled: true,
  hasSymbolTooltip: true,
} as const;

export const MARKET_DATA_WIDGET_CONFIG = {
  symbolsGroups: [
    {
      name: 'Indices',
      originalName: 'Indices',
      symbols: [
        { name: 'FOREXCOM:SPXUSD', displayName: 'S&P 500' },
        { name: 'FOREXCOM:NAS100USD', displayName: 'NASDAQ 100' },
        { name: 'FOREXCOM:DJI', displayName: 'Dow 30' },
      ],
    },
    {
      name: 'Forex',
      originalName: 'Forex',
      symbols: [
        { name: 'FX:EURUSD', displayName: 'EUR/USD' },
        { name: 'FX:GBPUSD', displayName: 'GBP/USD' },
        { name: 'FX:USDJPY', displayName: 'USD/JPY' },
      ],
    },
  ],
  showSymbolLogo: true,
  colorTheme: 'dark',
  isTransparent: false,
  displayMode: 'adaptive',
  locale: 'en',
} as const;

export const MARKET_OVERVIEW_WIDGET_CONFIG = {
  colorTheme: 'dark',
  dateRange: '12M',
  showChart: true,
  locale: 'en',
  largeChartUrl: '',
  isTransparent: false,
  showSymbolLogo: false,
  showFloatingTooltip: false,
  width: '100%',
  height: '100%',
  plotLineColorGrowing: '#2962FF',
  plotLineColorFalling: '#2962FF',
  gridLineColor: 'rgba(42, 46, 57, 1)',
  scaleFontColor: 'rgba(120, 123, 134, 1)',
  belowLineFillColorGrowing: 'rgba(41, 98, 255, 0.12)',
  belowLineFillColorFalling: 'rgba(41, 98, 255, 0.12)',
  belowLineFillColorGrowingBottom: 'rgba(41, 98, 255, 0)',
  belowLineFillColorFallingBottom: 'rgba(41, 98, 255, 0)',
  symbolActiveColor: 'rgba(41, 98, 255, 0.12)',
} as const;

// TradingView Widget Config Functions (for symbol-specific widgets)
export function SYMBOL_INFO_WIDGET_CONFIG(symbol: string) {
  return {
    symbol: symbol.toUpperCase(),
    colorTheme: 'dark',
    locale: 'en',
    isTransparent: false,
    displayMode: 'regular',
    largeChartUrl: '',
  };
}

export function CANDLE_CHART_WIDGET_CONFIG(symbol: string) {
  return {
    symbol: symbol.toUpperCase(),
    interval: 'D',
    container_id: 'tradingview_chart',
    datafeed: 'https://demo_feed.tradingview.com',
    library_path: '/charting_library/',
    locale: 'en',
    disabled_features: ['use_localstorage_for_settings'],
    enabled_features: ['study_templates'],
    charts_storage_url: 'https://saveload.tradingview.com',
    charts_storage_api_version: '1.1',
    client_id: 'tradingview.com',
    user_id: 'public_user_id',
    fullscreen: false,
    autosize: true,
    studies_overrides: {},
    colorTheme: 'dark',
  };
}

export function TECHNICAL_ANALYSIS_WIDGET_CONFIG(symbol: string) {
  return {
    symbol: symbol.toUpperCase(),
    interval: '1M',
    container_id: 'tradingview_technical_analysis',
    locale: 'en',
    colorTheme: 'dark',
    autosize: true,
    showVolume: false,
    hide_side_toolbar: false,
    allow_symbol_change: true,
    studies: [
      'MASimple@tv-basicstudies',
    ],
    support_host: 'https://www.tradingview.com',
  };
}

export function COMPANY_PROFILE_WIDGET_CONFIG(symbol: string) {
  return {
    symbol: symbol.toUpperCase(),
    colorTheme: 'dark',
    isTransparent: false,
    locale: 'en',
  };
}

export function COMPANY_FINANCIALS_WIDGET_CONFIG(symbol: string) {
  return {
    symbol: symbol.toUpperCase(),
    colorTheme: 'dark',
    isTransparent: false,
    locale: 'en',
  };
}

// News and Popular Symbols
export const NEWS_SYMBOLS = [
  'AAPL',
  'MSFT',
  'GOOGL',
  'AMZN',
  'TSLA',
  'META',
  'NVDA',
  'JPM',
  'V',
  'JNJ',
] as const;

export const POPULAR_STOCK_SYMBOLS = [
  'AAPL',
  'MSFT',
  'GOOGL',
  'AMZN',
  'TSLA',
  'META',
  'NVDA',
  'JPM',
  'V',
  'JNJ',
  'WMT',
  'PG',
  'MA',
  'UNH',
  'HD',
  'DIS',
  'BAC',
  'ADBE',
  'NFLX',
  'CRM',
] as const;

// Form Options
export const INVESTMENT_GOALS = [
  { value: 'Growth', label: 'Growth' },
  { value: 'Income', label: 'Income' },
  { value: 'Balance', label: 'Balance' },
  { value: 'Preservation', label: 'Capital Preservation' },
  { value: 'Retirement', label: 'Retirement Planning' },
] as const;

export const RISK_TOLERANCE_OPTIONS = [
  { value: 'Low', label: 'Low Risk' },
  { value: 'Medium', label: 'Medium Risk' },
  { value: 'High', label: 'High Risk' },
  { value: 'Very High', label: 'Very High Risk' },
] as const;

export const PREFERRED_INDUSTRIES = [
  { value: 'Technology', label: 'Technology' },
  { value: 'Healthcare', label: 'Healthcare' },
  { value: 'Finance', label: 'Finance' },
  { value: 'Energy', label: 'Energy' },
  { value: 'Consumer', label: 'Consumer Goods' },
  { value: 'Industrial', label: 'Industrial' },
  { value: 'Real Estate', label: 'Real Estate' },
  { value: 'Utilities', label: 'Utilities' },
  { value: 'Materials', label: 'Materials' },
  { value: 'Communication', label: 'Communication Services' },
] as const;

/**
 * Constantes centralizadas del proyecto
 * Reemplaza magic numbers y strings hardcodeados
 */

import {
  Bell,
  BookOpen,
  Briefcase,
  Building2,
  CircleHelp,
  Download,
  FileSearch,
  Filter,
  Gauge,
  Home,
  Library,
  Lightbulb,
  LineChart,
  Newspaper,
  Receipt,
  Settings,
  Share2,
  Sparkles,
  Star,
  Target,
  TrendingUp,
  Workflow,
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

// Mensajes de error comunes. En espanol: los de AUTH_* los muestra el usuario
// en /sign-in y /sign-up a traves de las server actions, y una app es-ES no
// puede mostrar "Authentication failed" en el formulario de acceso.
export const ERROR_MESSAGES = {
  AUTH_FAILED: 'No se pudo iniciar sesión. Revisa tu correo y tu contraseña.',
  AUTH_UNAVAILABLE: 'El servicio de autenticación no está disponible ahora mismo. Inténtalo de nuevo en unos minutos.',
  INVALID_SYMBOL: 'Símbolo con formato no válido. Debe tener entre 1 y 10 caracteres y solo letras, números, puntos y guiones.',
  MISSING_API_KEY: 'Falta la clave de API. Revisa tus variables de entorno.',
  RATE_LIMIT_EXCEEDED: 'Has superado el límite de peticiones. Inténtalo de nuevo en unos minutos.',
  DATABASE_ERROR: 'No se pudo conectar con la base de datos. Inténtalo de nuevo.',
  EXTERNAL_API_ERROR: 'No se pudieron obtener los datos del servicio externo.',
  NOT_FOUND: 'No se encontró el recurso solicitado.',
  VALIDATION_ERROR: 'Los datos introducidos no son válidos.',
} as const;

// Etiquetas en espanol, alineadas con el titulo (H1) de cada pagina.
//
// Estructura de ARBOL, no de lista plana con prefijos: `children` crea la
// indentacion real y hace que "Cartera" agrupe sus cuatro vistas en vez de
// repetir "Cartera · " en cada etiqueta. Un href solo debe aparecer una vez:
// `Sidebar`, `NavItems` y `Breadcrumbs` leen de aqui, y las paginas huerfanas
// se descubren comparando las rutas del app/ con esta lista.
export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  children?: NavItem[];
};

export type NavSection = {
  title: string;
  items: NavItem[];
};

export const NAV_SECTIONS: NavSection[] = [
  {
    title: 'Principal',
    items: [{ href: '/inicio', label: 'Inicio', icon: Home }],
  },
  {
    title: 'Cartera',
    items: [
      { href: '/portfolio', label: 'Resumen', icon: Briefcase },
      { href: '/portfolio/intelligence', label: 'Inteligencia', icon: Sparkles },
      { href: '/risk', label: 'Exposiciones', icon: Gauge },
      { href: '/taxes', label: 'Impuestos', icon: Receipt },
      { href: '/corporate-actions', label: 'Acciones corp.', icon: Building2 },
    ],
  },
  {
    title: 'Analisis',
    items: [
      {
        href: '/research',
        label: 'Research',
        icon: FileSearch,
        children: [
          { href: '/research/news', label: 'Noticias', icon: Newspaper },
          { href: '/research/sources', label: 'Fuentes', icon: Library },
          { href: '/research/workflows', label: 'Workflows', icon: Workflow },
          { href: '/research/settings', label: 'Ajustes', icon: Settings },
        ],
      },
      {
        href: '/screeners',
        label: 'Screeners',
        icon: Filter,
        children: [{ href: '/screener', label: 'Vista de mercado', icon: LineChart }],
      },
      {
        href: '/knowledge',
        label: 'Conocimiento',
        icon: BookOpen,
        children: [{ href: '/knowledge-graph', label: 'Grafo', icon: Share2 }],
      },
    ],
  },
  {
    title: 'Senales',
    items: [
      { href: '/watchlist', label: 'Watchlist', icon: Star },
      { href: '/movers', label: 'Movers', icon: TrendingUp },
      { href: '/insider', label: 'Insider', icon: Users },
      { href: '/ownership', label: '13F', icon: Landmark },
      { href: '/alerts', label: 'Alertas', icon: Bell },
      { href: '/propicks', label: 'ProPicks', icon: Lightbulb },
    ],
  },
  {
    title: 'Mi plan',
    items: [
      { href: '/plan', label: 'Plan', icon: Target },
      { href: '/export', label: 'Exportar', icon: Download },
    ],
  },
  {
    title: 'Sistema',
    // /security vive en el menu del avatar y /screener como hijo de Screeners.
    items: [{ href: '/help', label: 'Ayuda', icon: CircleHelp }],
  },
];

/** Aplana el arbol a una lista de rutas, para buscar un href puntual. */
export function flattenNavItems(sections: NavSection[] = NAV_SECTIONS): NavItem[] {
  return sections.flatMap((section) =>
    section.items.flatMap((item) => (item.children ? [item, ...item.children] : [item])),
  );
}

/**
 * Un href esta activo si es el mas largo que coincide con la ruta: con
 * `pathname.startsWith(href)` a secas, /portfolio/intelligence encendia
 * "Cartera" y "Cartera · Intelligence" a la vez.
 */
export function isNavItemActive(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/';
  if (pathname === href) return true;
  if (!pathname.startsWith(`${href}/`)) return false;
  // Un ancestro no se ilumina si existe un destino mas especifico que tambien
  // coincide: en /portfolio/intelligence solo se enciende "Inteligencia".
  const hasMoreSpecificMatch = flattenNavItems().some(
    (item) =>
      item.href !== href && (pathname === item.href || pathname.startsWith(`${item.href}/`)),
  );
  return !hasMoreSpecificMatch;
}

/** Encabezado de seccion visible solo si la seccion aporta mas de un destino. */
export function showsNavSectionTitle(section: NavSection): boolean {
  return section.items.length > 1;
}

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
  { value: "utilities", label: "Servicios públicos" },
  { value: "communication", label: "Comunicación" }
] as const;

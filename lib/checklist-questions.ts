// Constantes del checklist - puede ser importado en cliente
// Checklist Value Investing mejorado con 18 preguntas críticas y umbrales específicos
export const CHECKLIST_QUESTIONS = [
    // === NEGOCIO Y MOAT ===
    {
        id: 'understand_business',
        category: 'Negocio',
        question: '¿Entiendo cómo gana dinero esta empresa y su modelo de negocio?',
        weight: 1,
        metric: null,
        threshold: null
    },
    {
        id: 'competitive_moat',
        category: 'Moat',
        question: '¿Tiene una ventaja competitiva duradera (marca, patentes, efectos de red, costes de cambio)?',
        weight: 2,
        metric: 'roic',
        threshold: '> 15% durante 5+ años indica moat'
    },
    {
        id: 'pricing_power',
        category: 'Moat',
        question: '¿Puede subir precios por encima de la inflación sin perder clientes?',
        weight: 1.5,
        metric: 'grossMargin',
        threshold: 'Margen bruto estable o creciente'
    },
    {
        id: 'recurring_revenue',
        category: 'Negocio',
        question: '¿Tiene ingresos recurrentes, suscripciones o contratos a largo plazo?',
        weight: 1.5,
        metric: 'revenueGrowth',
        threshold: 'Ingresos predecibles y crecientes'
    },

    // === MANAGEMENT ===
    {
        id: 'management_quality',
        category: 'Management',
        question: '¿El equipo directivo tiene track record de ejecución y transparencia?',
        weight: 1.5,
        metric: null,
        threshold: 'Historial de cumplir guidance'
    },
    {
        id: 'skin_in_game',
        category: 'Management',
        question: '¿Los directivos poseen acciones significativas (>1% o >$10M)?',
        weight: 1.5,
        metric: 'insiderOwnership',
        threshold: '> 1% propiedad insider'
    },
    {
        id: 'insider_buying',
        category: 'Management',
        question: '¿Hay compras de insiders recientes (últimos 6 meses)?',
        weight: 1.5,
        metric: 'insiderTransactions',
        threshold: 'Compras netas > ventas'
    },
    {
        id: 'capital_allocation',
        category: 'Management',
        question: '¿La empresa asigna bien el capital (buenos M&A, recompras a buen precio, dividendos sostenibles)?',
        weight: 1.5,
        metric: 'roic',
        threshold: 'ROIC > WACC consistentemente'
    },

    // === CALIDAD FINANCIERA ===
    {
        id: 'earnings_quality',
        category: 'Financiero',
        question: '¿Los beneficios son de alta calidad (FCF/Net Income > 80%)?',
        weight: 2,
        metric: 'fcfConversion',
        threshold: 'FCF / Net Income > 0.8'
    },
    {
        id: 'free_cash_flow',
        category: 'Financiero',
        question: '¿Genera Free Cash Flow positivo y creciente consistentemente?',
        weight: 2,
        metric: 'freeCashFlow',
        threshold: 'FCF positivo últimos 5 años'
    },
    {
        id: 'return_on_capital',
        category: 'Financiero',
        question: '¿El ROIC es superior al 12% de forma sostenida (mejor si > 20%)?',
        weight: 2,
        metric: 'roic',
        threshold: 'ROIC > 12% (excelente > 20%)'
    },
    {
        id: 'margin_stability',
        category: 'Financiero',
        question: '¿Los márgenes operativos se han mantenido o expandido en 5 años?',
        weight: 1.5,
        metric: 'operatingMargin',
        threshold: 'Margen estable o creciente 5Y'
    },

    // === BALANCE Y RIESGO ===
    {
        id: 'debt_level',
        category: 'Balance',
        question: '¿La deuda es manejable (Deuda Neta/EBITDA < 2x)?',
        weight: 1.5,
        metric: 'debtToEbitda',
        threshold: 'Net Debt/EBITDA < 2x'
    },
    {
        id: 'strong_balance',
        category: 'Balance',
        question: '¿Tiene balance sólido (caja > deuda corto plazo, current ratio > 1.5)?',
        weight: 1.5,
        metric: 'currentRatio',
        threshold: 'Current Ratio > 1.5'
    },
    {
        id: 'no_major_risks',
        category: 'Riesgos',
        question: '¿Los riesgos están identificados (regulatorio, competencia, concentración)?',
        weight: 1.5,
        metric: null,
        threshold: 'Sin red flags obvios'
    },

    // === VALORACIÓN ===
    {
        id: 'margin_of_safety',
        category: 'Valoración',
        question: '¿El precio ofrece margen de seguridad vs valor intrínseco (>20%)?',
        weight: 2,
        metric: 'dcfUpside',
        threshold: 'Upside > 20% vs DCF'
    },
    {
        id: 'valuation_vs_history',
        category: 'Valoración',
        question: '¿Cotiza por debajo de su media histórica de P/E o EV/EBITDA?',
        weight: 1.5,
        metric: 'peRatio',
        threshold: 'P/E < media 5Y'
    },

    // === CRECIMIENTO Y SECTOR ===
    {
        id: 'growth_potential',
        category: 'Crecimiento',
        question: '¿Tiene runway de crecimiento para los próximos 5-10 años?',
        weight: 1,
        metric: 'revenueGrowth',
        threshold: 'Crecimiento > inflación + 5%'
    },
    {
        id: 'industry_tailwinds',
        category: 'Sector',
        question: '¿El sector tiene vientos de cola seculares favorables?',
        weight: 1,
        metric: null,
        threshold: 'Tendencias macro positivas'
    },

    // === CONVICCIÓN FINAL ===
    {
        id: 'would_hold_10_years',
        category: 'Convicción',
        question: '¿Mantendría esta acción 10 años sin mirar el precio diariamente?',
        weight: 2,
        metric: null,
        threshold: 'Test final de Buffett'
    }
] as const;

export type ChecklistQuestionType = typeof CHECKLIST_QUESTIONS[number];

// Categorías ordenadas para UI
export const CHECKLIST_CATEGORIES = [
    { id: 'Negocio', label: 'Negocio y Moat', icon: '🏢' },
    { id: 'Moat', label: 'Ventaja Competitiva', icon: '🏰' },
    { id: 'Management', label: 'Gestión', icon: '👔' },
    { id: 'Financiero', label: 'Calidad Financiera', icon: '📊' },
    { id: 'Balance', label: 'Balance y Riesgo', icon: '⚖️' },
    { id: 'Riesgos', label: 'Riesgos', icon: '⚠️' },
    { id: 'Valoración', label: 'Valoración', icon: '💰' },
    { id: 'Crecimiento', label: 'Crecimiento', icon: '📈' },
    { id: 'Sector', label: 'Sector', icon: '🌐' },
    { id: 'Convicción', label: 'Convicción Final', icon: '💎' }
] as const;

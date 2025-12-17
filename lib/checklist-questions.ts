// Constantes del checklist - puede ser importado en cliente
export const CHECKLIST_QUESTIONS = [
    {
        id: 'understand_business',
        category: 'Negocio',
        question: '¿Entiendo cómo gana dinero esta empresa?',
        weight: 1
    },
    {
        id: 'competitive_moat',
        category: 'Moat',
        question: '¿Tiene una ventaja competitiva duradera (moat)?',
        weight: 2
    },
    {
        id: 'pricing_power',
        category: 'Moat',
        question: '¿Puede subir precios sin perder clientes?',
        weight: 1.5
    },
    {
        id: 'recurring_revenue',
        category: 'Negocio',
        question: '¿Tiene ingresos recurrentes o predecibles?',
        weight: 1.5
    },
    {
        id: 'management_quality',
        category: 'Management',
        question: '¿El equipo directivo es honesto y competente?',
        weight: 1.5
    },
    {
        id: 'skin_in_game',
        category: 'Management',
        question: '¿Los directivos tienen participación significativa?',
        weight: 1
    },
    {
        id: 'debt_level',
        category: 'Financiero',
        question: '¿El nivel de deuda es manejable (Debt/EBITDA < 3)?',
        weight: 1.5
    },
    {
        id: 'free_cash_flow',
        category: 'Financiero',
        question: '¿Genera Free Cash Flow positivo y consistente?',
        weight: 2
    },
    {
        id: 'return_on_capital',
        category: 'Financiero',
        question: '¿El ROIC/ROE es superior al 15% sostenido?',
        weight: 1.5
    },
    {
        id: 'margin_of_safety',
        category: 'Valoración',
        question: '¿El precio actual ofrece margen de seguridad (>25%)?',
        weight: 2
    },
    {
        id: 'growth_potential',
        category: 'Crecimiento',
        question: '¿Tiene potencial de crecimiento para los próximos 5 años?',
        weight: 1
    },
    {
        id: 'industry_tailwinds',
        category: 'Sector',
        question: '¿El sector tiene vientos de cola favorables?',
        weight: 1
    },
    {
        id: 'no_major_risks',
        category: 'Riesgos',
        question: '¿Están identificados y son manejables los principales riesgos?',
        weight: 1.5
    },
    {
        id: 'capital_allocation',
        category: 'Management',
        question: '¿La empresa asigna bien el capital (dividendos, recompras, M&A)?',
        weight: 1
    },
    {
        id: 'would_hold_10_years',
        category: 'Convicción',
        question: '¿Mantendría esta acción durante 10 años sin mirar el precio?',
        weight: 2
    }
] as const;

export type ChecklistQuestionType = typeof CHECKLIST_QUESTIONS[number];

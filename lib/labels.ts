/**
 * Etiquetas visibles para valores que el backend codifica en inglés.
 *
 * El `value` de los <select>/query params DEBE seguir siendo la clave
 * inglesa (el backend la espera tal cual); lo que se traduce es solo lo que
 * el usuario lee. Compartido por el Screener y por los filtros de ProPicks,
 * que antes tenían dos listas de sectores distintas.
 */
export const SECTORES: Record<string, string> = {
  Technology: 'Tecnología',
  'Information Technology': 'Tecnología',
  Healthcare: 'Salud',
  'Health Care': 'Salud',
  'Financial Services': 'Servicios financieros',
  Financials: 'Servicios financieros',
  'Consumer Discretionary': 'Consumo cíclico',
  'Consumer Cyclical': 'Consumo cíclico',
  Industrials: 'Industriales',
  'Consumer Staples': 'Consumo básico',
  Energy: 'Energía',
  Utilities: 'Servicios públicos',
  'Real Estate': 'Inmobiliario',
  Materials: 'Materiales',
  'Communication Services': 'Servicios de comunicación',
  Media: 'Medios',
};

/** Etiqueta ES de un sector; si el backend manda uno desconocido, se muestra tal cual. */
export function etiquetaSector(value: string): string {
  return SECTORES[value] ?? value;
}

/** Etiqueta ES del tier de fuente (F175): el token interno
 *  («tier_1_regulatory») no se muestra tal cual; desconocido -> tal cual. */
// Las ocho claves del catálogo backend (source_hierarchy_service.SOURCE_TIERS).
// Si el backend añade una clave nueva, aquí debe llegar su etiqueta; hasta
// entonces se muestra el código crudo (visible y honesto, nunca inventado).
const TIERS_FUENTE: Record<string, string> = {
  tier_1_regulatory: 'Regulatoria · T1',
  tier_2_company: 'Empresa · T2',
  tier_3_transcript: 'Transcripción · T3',
  tier_4_reputable_media: 'Medios · T4',
  tier_5_data_provider: 'Proveedor de datos · T5',
  tier_6_bootstrap: 'Datos iniciales · T6',
  tier_7_user_input: 'Aportado por el usuario · T7',
  tier_unknown: 'Fuente sin clasificar',
};

export function etiquetaTierFuente(value: string): string {
  return TIERS_FUENTE[value] ?? value;
}

/** Etiqueta ES del tipo de evento de noticias (F175). */
const TIPOS_EVENTO: Record<string, string> = {
  regulatory: 'Regulatorio',
  earnings: 'Resultados',
  dilution: 'Dilución',
  contract: 'Contrato',
  capital_allocation: 'Asignación de capital',
  general_news: 'Noticia general',
  macro: 'Macro',
  opinion: 'Opinión',
  unknown: 'Desconocido',
};

export function etiquetaTipoEvento(value: string): string {
  return TIPOS_EVENTO[value] ?? value;
}

/** Etiqueta ES del tipo de instrumento del buscador (F174): Finnhub devuelve
 *  «Common Stock», «Canadian DR»... y se pintaban en inglés. */
const TIPOS_INSTRUMENTO: Record<string, string> = {
  'Common Stock': 'Acción ordinaria',
  'Preferred Stock': 'Acción preferente',
  'Canadian DR': 'Recibo de depósito canadiense',
  ADR: 'ADR',
  ETF: 'ETF',
  ETN: 'ETN',
  ETP: 'ETP',
  REIT: 'REIT',
  Warrant: 'Warrant',
  Right: 'Derecho',
  Unit: 'Unidad',
};

export function etiquetaTipoInstrumento(value: string): string {
  return TIPOS_INSTRUMENTO[value] ?? value;
}

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
  Healthcare: 'Salud',
  'Health Care': 'Salud',
  'Financial Services': 'Servicios financieros',
  'Consumer Discretionary': 'Consumo cíclico',
  'Consumer Cyclical': 'Consumo cíclico',
  Industrials: 'Industriales',
  'Consumer Staples': 'Consumo básico',
  Energy: 'Energía',
  Utilities: 'Servicios públicos',
  'Real Estate': 'Inmobiliario',
  Materials: 'Materiales',
  'Communication Services': 'Servicios de comunicación',
};

/** Etiqueta ES de un sector; si el backend manda uno desconocido, se muestra tal cual. */
export function etiquetaSector(value: string): string {
  return SECTORES[value] ?? value;
}

/**
 * La API /api/portfolio/summary devuelve `cash` como diccionario por
 * moneda ya convertido a divisa base (RiskService.dashboard →
 * calculate_portfolio_risk: { [baseCurrency]: cash_base }). El frontend
 * necesita un único importe en divisa base: la suma de los valores.
 * Si el backend no envía caja, el importe es 0 y la línea no se muestra.
 */
export function sumCashByCurrency(cash: Record<string, number> | null | undefined): number {
    if (!cash || typeof cash !== 'object') {
        return 0;
    }
    return Object.values(cash).reduce(
        (sum, value) => sum + (typeof value === 'number' && Number.isFinite(value) ? value : 0),
        0,
    );
}

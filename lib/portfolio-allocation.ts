/**
 * Datos del donut de distribución de /portfolio. Decisión de producto
 * (Nico, 11 oct 2026): los pesos se reparten SOLO entre las posiciones
 * (suman 100%) y la caja/margen se muestra como línea aparte fuera del
 * donut. Con caja negativa (margen), pesos sobre el valor total darían
 * porcentajes >100%: matemáticamente cierto y visualmente absurdo.
 */
export type AllocationHolding = {
    symbol: string;
    value: number;
    gain: number;
    gainPercent: number;
};

export type AllocationSliceData = AllocationHolding & {
    percentage: number;
};

/** Símbolo reservado de la caja. Ya no es segmento del donut; lo conserva
 *  AllocationTooltip por compatibilidad con datos antiguos. */
export const CASH_SLICE_SYMBOL = "Caja";

export function buildAllocationSlices(holdings: AllocationHolding[]): AllocationSliceData[] {
    const positionsValue = holdings.reduce((sum, holding) => sum + holding.value, 0);
    return holdings
        .map((holding) => ({
            symbol: holding.symbol,
            value: holding.value,
            gain: holding.gain,
            gainPercent: holding.gainPercent,
            percentage: positionsValue > 0 ? (holding.value / positionsValue) * 100 : 0,
        }))
        .sort((a, b) => b.value - a.value);
}

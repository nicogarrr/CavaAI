/**
 * Datos del donut de distribución de /portfolio. La etiqueta declara
 * "pesos sobre el valor total (caja incluida)", así que la caja entra como
 * segmento propio: sin ella el círculo se llenaba solo con acciones.
 * Con cartera solo-caja (sin posiciones) el donut es 100% Caja.
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

export const CASH_SLICE_SYMBOL = 'Caja';

export function buildAllocationSlices(
    holdings: AllocationHolding[],
    totalValue: number,
    cash?: number | null,
): AllocationSliceData[] {
    const slices: AllocationSliceData[] = holdings
        .map((holding) => ({
            symbol: holding.symbol,
            value: holding.value,
            gain: holding.gain,
            gainPercent: holding.gainPercent,
            percentage: totalValue > 0 ? (holding.value / totalValue) * 100 : 0,
        }))
        .sort((a, b) => b.value - a.value);
    if (typeof cash === 'number' && cash > 0 && totalValue > 0) {
        slices.push({
            symbol: CASH_SLICE_SYMBOL,
            value: cash,
            gain: 0,
            gainPercent: 0,
            percentage: (cash / totalValue) * 100,
        });
    }
    return slices;
}

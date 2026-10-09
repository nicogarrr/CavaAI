// Qué mostrar de una posición en Inicio. El valor convertido y el coste son
// disponibilidades distintas: sin base de coste no hay rentabilidad (N/D), pero
// el valor sigue siendo válido si su conversión existe.
export type HoldingDisplayInput = {
    cost: number;
    value: number;
    valueMissing: boolean;
    fxMissing: boolean;
};

export type HoldingDisplayMode = 'gain' | 'value' | 'na';

export function holdingDisplayMode(h: HoldingDisplayInput): HoldingDisplayMode {
    if (h.cost > 0 && !h.fxMissing) return 'gain';
    if (!h.valueMissing && h.value > 0) return 'value';
    return 'na';
}

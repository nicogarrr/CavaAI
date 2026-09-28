/**
 * Estado de la tarjeta de índices a partir de SU PROPIO resultado
 * (datos/error), nunca inferido de una petición vecina: una ruta caída no
 * apaga la tarjeta de la otra y viceversa.
 */
export type IndicesCardState = 'data' | 'empty' | 'unavailable';

export function indicesCardState(
    validCount: number,
    error: unknown,
    isUnavailable: (error: unknown) => boolean,
): IndicesCardState {
    if (validCount > 0) return 'data';
    return isUnavailable(error) ? 'unavailable' : 'empty';
}

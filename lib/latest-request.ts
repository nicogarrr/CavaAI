/**
 * Sello de "petición más reciente" para búsquedas con debounce (F215, race
 * del auditor): una respuesta tardía de una query vieja no debe pisar los
 * resultados (ni el error) de la query nueva. Cada llamada pide un ticket en
 * `begin()`; al resolver, solo se aplica si `isLatest(ticket)`.
 */
export interface LatestRequestGate {
    begin(): number;
    invalidate(): void;
    isLatest(ticket: number): boolean;
}

export function createLatestRequestGate(): LatestRequestGate {
    let latest = 0;
    return {
        begin() {
            latest += 1;
            return latest;
        },
        invalidate() {
            // Invalida cualquier petición en vuelo en el momento en que la
            // query cambia (no cuando dispara el debounce): una respuesta
            // tardía ya no puede pintar sobre el estado nuevo.
            latest += 1;
        },
        isLatest(ticket: number) {
            return ticket === latest;
        },
    };
}

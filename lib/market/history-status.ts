// Estado honesto de la tarjeta «Historial de precio · 1 año».
//
// La insignia describe la SERIE, no la cotización puntual: antes bastaba
// una quote sin velas para etiquetar «parcial», y el panel enseñaba a la
// vez «Historial de precio no disponible» (F161). Ahora:
//   - sin sesiones -> «no disponible» (aunque la quote puntual cargue);
//   - pocas sesiones -> «parcial» y la UI muestra el tramo con aviso;
//   - resto -> «disponible».
// Un año tiene ~252 sesiones bursátiles; por debajo del 80% se considera
// serie incompleta.
export const HISTORY_PARTIAL_MIN_SESSIONS = 200;

export type MarketHistoryStatus = 'available' | 'partial' | 'unavailable';

export function marketHistoryStatus(sessions: number): MarketHistoryStatus {
    if (!Number.isFinite(sessions) || sessions <= 0) return 'unavailable';
    return sessions < HISTORY_PARTIAL_MIN_SESSIONS ? 'partial' : 'available';
}

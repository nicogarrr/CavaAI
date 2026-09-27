/**
 * F65: la tarjeta «Oportunidades por valor intrínseco» del inicio declaraba
 * alcance de universo («Todo el universo del screener», «Ninguna empresa del
 * universo supera hoy un 5 %…») probando solo las primeras 6 candidatas y
 * tratando igual un DCF fallido que un potencial insuficiente. Aquí vive el
 * alcance real de la sonda y los textos honestos que lo declaran.
 */

/** Candidatas del screener que se prueban por visita (DCF + precio). */
export const DCF_CANDIDATE_LIMIT = 6;

/** Umbral de potencial (%) para listar una oportunidad. */
export const DCF_MIN_UPSIDE_PCT = 5;

export type DcfProbeOutcome<T> = {
    /** true = el DCF y el precio se pudieron leer (la candidata cuenta). */
    evaluated: boolean;
    opportunity: T | null;
};

export type DcfScope = {
    /** Candidatas intentadas (como mucho DCF_CANDIDATE_LIMIT). */
    probed: number;
    /** Con DCF y precio válidos. */
    evaluated: number;
    /** Sin DCF/precio o con error: no dicen nada sobre su potencial. */
    failed: number;
};

export function summarizeDcfProbe<T>(outcomes: DcfProbeOutcome<T>[]): DcfScope {
    const evaluated = outcomes.filter((outcome) => outcome.evaluated).length;
    return { probed: outcomes.length, evaluated, failed: outcomes.length - evaluated };
}

/** Alcance real cuando hay oportunidades que mostrar. */
export function dcfScopeNote(scope: DcfScope, marketCapLabel: string): string {
    const base = `Las ${scope.probed} primeras candidatas del screener (market cap > ${marketCapLabel}), sin filtro de sector`;
    return scope.failed > 0 ? `${base}; ${scope.failed} no se pudieron evaluar.` : `${base}.`;
}

/**
 * Estado vacío honesto: distingue «evaluadas y ninguna supera el umbral» de
 * «no se pudo evaluar», que no permite concluir nada sobre el potencial.
 */
export function dcfEmptyNote(scope: DcfScope): string {
    if (scope.probed === 0) {
        return 'El screener no devolvió candidatas sobre las que calcular el valor intrínseco.';
    }
    if (scope.evaluated === 0) {
        return `No se pudo calcular el valor intrínseco de las ${scope.probed} candidatas del screener probadas.`;
    }
    const base = `Ninguna de las ${scope.evaluated} candidatas del screener evaluadas supera hoy un ${DCF_MIN_UPSIDE_PCT} % de potencial sobre su valor intrínseco`;
    return scope.failed > 0 ? `${base}; ${scope.failed} no se pudieron evaluar.` : `${base}.`;
}

/**
 * Copy del estado y la puntuación de una auditoría de fuentes (F243).
 *
 * Verdad del backend (source_auditor.py): la puntuación mide SOLO
 * afirmaciones materiales con fuente citada, menos 5 puntos por afirmación
 * de baja confianza. El bloqueo (passed=false) puede venir de afirmaciones
 * sin fuente, conflictos de datos o ausencia de traza de valoración — dos
 * de esas tres causas NO mueven la puntuación. Por eso una auditoría
 * bloqueada puede mostrar 100/100 y el texto debe decir qué mide y qué no.
 */

export function auditStatusLabel(passed: boolean): string {
    return passed ? 'superada' : 'bloqueada';
}

export function auditScoreText(
    passed: boolean,
    score: number,
    formatScore: (value: number) => string,
): string {
    const base = `puntuación de respaldo de afirmaciones ${formatScore(score)}/100 (penaliza baja confianza)`;
    return passed
        ? base
        : `${base} — mide solo citas, no el motivo del bloqueo`;
}

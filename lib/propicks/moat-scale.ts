/**
 * quality_moat_score_v2 es un recuento de criterios superados (0 a 8), NO una
 * puntuación 0-100. Tratarlo como 0-100 hundía profitability a ~8 y dejaba el
 * score de TODOS los picks por debajo del filtro de 70 (Top 0). Módulo puro,
 * sin imports, para poder probarlo con node:test.
 */
export const MOAT_V2_MAX_CHECKS = 8;

/** Convierte el recuento de criterios (0-8) a escala 0-100, redondeado a 1 decimal. */
export function moatChecksToScore(checks: number): number {
    const clamped = Math.max(0, Math.min(MOAT_V2_MAX_CHECKS, checks));
    return Math.round((clamped / MOAT_V2_MAX_CHECKS) * 1000) / 10;
}

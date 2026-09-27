/**
 * F318: estadística de volumen sobre velas con huecos HONESTOS.
 * Un volumen desconocido (null) no entra en las medias — un 0 inventado
 * arrastraba la media y podía dar 0/0 en el cambio porcentual. Con datos
 * conocidos insuficientes para comparar dos ventanas de 20, no hay
 * estadística (null) en vez de una cifra aparentada.
 */

export type VolumeTrend = 'increasing' | 'decreasing' | 'stable';

export type VolumeStats = {
    avgVolume: number;
    volumeTrend: VolumeTrend | null;
};

const WINDOW = 20;

export function volumeTrendStats(volumes: (number | null)[]): VolumeStats | null {
    const known = volumes.filter((volume): volume is number => volume !== null);
    // Una ventana reciente COMPLETA de sesiones conocidas como mínimo: con
    // menos, cualquier media aparenta una precisión que el dato no tiene.
    if (known.length < WINDOW) return null;
    const recent = known.slice(-WINDOW);
    const avgVolume = recent.reduce((acc, volume) => acc + volume, 0) / recent.length;
    // La tendencia compara DOS ventanas completas de 20 conocidas: una
    // ventana previa de 1-19 sesiones no es comparable con una de 20
    // (19 huecos + 1 dato marcaban 'increasing' sin base estadística).
    const previous = known.slice(-WINDOW * 2, -WINDOW);
    if (previous.length < WINDOW) return { avgVolume, volumeTrend: null };
    const previousAvg = previous.reduce((acc, volume) => acc + volume, 0) / previous.length;
    if (previousAvg === 0) return { avgVolume, volumeTrend: null };
    const changePercent = ((avgVolume - previousAvg) / previousAvg) * 100;
    if (changePercent > 10) return { avgVolume, volumeTrend: 'increasing' };
    if (changePercent < -10) return { avgVolume, volumeTrend: 'decreasing' };
    return { avgVolume, volumeTrend: 'stable' };
}

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
/** Mínimo de sesiones con volumen conocido para comparar dos ventanas. */
const MIN_KNOWN = WINDOW + 1;

export function volumeTrendStats(volumes: (number | null)[]): VolumeStats | null {
    const known = volumes.filter((volume): volume is number => volume !== null);
    if (known.length < MIN_KNOWN) return null;
    const recent = known.slice(-WINDOW);
    const previous = known.slice(-WINDOW * 2, -WINDOW);
    const avgVolume = recent.reduce((acc, volume) => acc + volume, 0) / recent.length;
    if (previous.length === 0) return { avgVolume, volumeTrend: null };
    const previousAvg = previous.reduce((acc, volume) => acc + volume, 0) / previous.length;
    if (previousAvg === 0) return { avgVolume, volumeTrend: null };
    const changePercent = ((avgVolume - previousAvg) / previousAvg) * 100;
    if (changePercent > 10) return { avgVolume, volumeTrend: 'increasing' };
    if (changePercent < -10) return { avgVolume, volumeTrend: 'decreasing' };
    return { avgVolume, volumeTrend: 'stable' };
}

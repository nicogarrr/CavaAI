export const SPARK_WIDTH = 120;
export const SPARK_HEIGHT = 36;

/**
 * Puntos del sparkline (viewBox SPARK_WIDTH x SPARK_HEIGHT). Menos de dos
 * cierres no dibuja nada: una línea de un punto fingiría una tendencia.
 */
export function sparklinePoints(closes: number[]): string {
    if (closes.length < 2) return '';
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const span = max - min || 1;
    return closes
        .map((close, index) => {
            const x = (index / (closes.length - 1)) * SPARK_WIDTH;
            const y = SPARK_HEIGHT - ((close - min) / span) * SPARK_HEIGHT;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(' ');
}

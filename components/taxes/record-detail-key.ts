/**
 * F94: RecordDetail guarda el informe en su propio useState sin
 * resincronizar con la prop. La key fuerza remount cuando cambia el
 * ejercicio (year) y tras una regeneración (reportKey), para que el
 * contenido nunca sea del año equivocado.
 */
export function recordDetailKey(year: number, reportKey: number): string {
    return `${year}-${reportKey}`;
}

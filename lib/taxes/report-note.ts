/**
 * F183: nota honesta para un informe fiscal calculado AL VUELO. El GET es
 * de solo lectura: un ejercicio sin informe persistido se calcula en
 * memoria y llega con `persisted=false` y `generated_at=null`, así que la
 * fila «Generado» simplemente no existía y el usuario no podía saber si el
 * informe estaba guardado. Regla: sin `generated_at` y con
 * `persisted === false` -> nota junto a esa fila; cualquier otra
 * combinación (persistido, o dato ausente sin declarar) -> sin nota.
 */
export const ON_THE_FLY_REPORT_NOTE = 'Informe calculado al vuelo, aún no guardado';

export function onTheFlyReportNote(
    report: { generated_at?: unknown; persisted?: unknown } | null,
): string | null {
    if (!report) return null;
    if (report.generated_at) return null;
    return report.persisted === false ? ON_THE_FLY_REPORT_NOTE : null;
}

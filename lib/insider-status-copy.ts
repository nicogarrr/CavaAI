/**
 * Copy de estados no-ok del panel insider (F234). Puro y testeable: la
 * verdad del mensaje depende de QUÉ campos devolvió el backend.
 *
 * - degraded con contadores: «N con error de M escaneados».
 * - degraded solo con reason (catch global): cabecera explicativa común y
 *   la reason como DETALLE, nunca como sustituto — una razón técnica a pelo
 *   («AAPL: TypeError») sigue siendo opaca.
 * - partial sin señales: los escaneados no son «analizados» si algunos
 *   fallaron — se dice «X legibles de Y escaneados».
 */

export type InsiderStatusFields = {
    reason?: unknown;
    filings_scanned?: unknown;
    filings_parsed?: unknown;
    filings_failed?: unknown;
};

type CountText = (value: unknown) => string;

const asNumber = (value: unknown): number | null =>
    typeof value === 'number' && Number.isFinite(value) ? value : null;

export function degradedCopy(
    ticker: string,
    fields: InsiderStatusFields,
    countText: CountText,
): { header: string; detail: string | null } {
    const scanned = asNumber(fields.filings_scanned);
    const failed = asNumber(fields.filings_failed);
    // Con contadores sabemos que se escanearon Form 4 y todos fallaron; con
    // reason sola (catch global) el fallo pudo ser ANTES de consultar filings
    // (CIK, listado), asi que la cabecera abarca consulta y lectura.
    const header =
        scanned !== null && failed !== null
            ? `${ticker}: SEC EDGAR no devolvió ningún Form 4 legible (${countText(failed)} con error de ${countText(scanned)} escaneados).`
            : `${ticker}: no se pudieron consultar o leer las señales Form 4 de SEC EDGAR.`;
    const detail =
        typeof fields.reason === 'string' && fields.reason ? fields.reason : null;
    return { header, detail };
}

export function analyzedCountCopy(
    status: string,
    fields: InsiderStatusFields,
    countText: CountText,
): string {
    const scanned = asNumber(fields.filings_scanned);
    const parsed = asNumber(fields.filings_parsed);
    if (status === 'partial' && scanned !== null && parsed !== null) {
        return `${countText(parsed)} legibles de ${countText(scanned)} escaneados`;
    }
    return `${countText(fields.filings_scanned)} analizados`;
}

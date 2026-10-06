/**
 * El campo <value> del 13F se guarda tal cual (sin convertir). Hasta el informe
 * del T3 2022 la SEC lo pedia en MILES de dolares; desde los informes del
 * 31-12-2022 (formulario nuevo, ene 2023) va en DOLARES enteros. Se normaliza
 * por la fecha del informe y se devuelve siempre en dolares.
 * Fuente: SEC, Form 13F XML technical specification (EDGAR).
 */
const DOLLARS_FROM = '2022-12-31';

export function form13fValueToUsd(
    raw: number | null | undefined,
    reportDate: string | null | undefined,
): number | null {
    if (raw === null || raw === undefined || !reportDate) return null;
    return reportDate >= DOLLARS_FROM ? raw : raw * 1000;
}

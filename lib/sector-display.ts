/**
 * F106: el master guarda la cadena 'Unknown' en sector/industry cuando no
 * tiene clasificación (300 de 2115 empresas, p.ej. ALM, A3M). Mostrarla
 * cruda en la UI española es un placeholder en inglés que parece dato.
 * 'Unknown' se trata como ausencia: se omiten las partes sin dato y, si no
 * hay ninguna, la línea lo declara.
 */

const clean = (value: unknown): string | null =>
    typeof value === 'string' && value.trim() && value !== 'Unknown' ? value : null;

export function sectorIndustryLine(sector: unknown, industry: unknown): string {
    const parts = [clean(sector), clean(industry)].filter((p): p is string => p !== null);
    return parts.length ? parts.join(' · ') : 'Sector sin dato';
}

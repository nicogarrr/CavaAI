/**
 * F106: el master guarda la cadena 'Unknown' en sector/industry cuando no
 * tiene clasificación (300 de 2115 empresas, p.ej. ALM, A3M). Mostrarla
 * cruda en la UI española es un placeholder en inglés que parece dato.
 * 'Unknown' se trata como ausencia: se omiten las partes sin dato y, si no
 * hay ninguna, la línea lo declara.
 */

// Placeholder de ausencia en cualquier capitalización y con espacios
// (« Unknown », «unknown», «UNKNOWN»): se recorta y compara en minúsculas.
const clean = (value: unknown): string | null => {
    if (typeof value !== 'string') return null;
    const trimmed = value.trim();
    return trimmed && trimmed.toLowerCase() !== 'unknown' ? trimmed : null;
};

export function sectorIndustryLine(sector: unknown, industry: unknown): string {
    const parts = [clean(sector), clean(industry)].filter((p): p is string => p !== null);
    return parts.length ? parts.join(' · ') : 'Sector sin dato';
}

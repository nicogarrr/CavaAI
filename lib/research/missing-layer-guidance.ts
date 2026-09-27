/**
 * Orientación por capa de research faltante (F305).
 *
 * El aviso «Capas de research que faltan» mandaba siempre a importar
 * documentos, incluso cuando lo que falta es la tesis o el modelo: importar
 * fuentes no genera ninguna de las dos. Cada capa tiene su destino y su
 * verbo; una capa desconocida NO inventa ruta (sin enlace).
 */

export const MISSING_LAYER_LABELS: Record<string, string> = {
    documents: 'documentos',
    financial_facts: 'hechos financieros',
    thesis: 'tesis',
    long_term_model: 'modelo a largo plazo',
};

export function missingLayerLabel(layer: string): string {
    const known = MISSING_LAYER_LABELS[layer];
    if (known) return known;
    // Capa no catalogada: se humaniza, nunca se oculta.
    const words = layer.replaceAll('_', ' ').trim();
    return words.charAt(0).toUpperCase() + words.slice(1);
}

export type MissingLayerAction = { href: string; label: string };

export function missingLayerAction(ticker: string, layer: string): MissingLayerAction | null {
    const base = `/research/${encodeURIComponent(ticker)}`;
    switch (layer) {
        case 'documents':
            return { href: `${base}?view=documents`, label: 'Importa una fuente primaria' };
        case 'financial_facts':
            // La vista financieros tiene los botones «Refrescar SEC/FMP/ESEF».
            return { href: `${base}?view=financieros`, label: 'Refresca los financieros' };
        case 'thesis':
            return { href: `${base}?view=tesis`, label: 'Abre la tesis para generarla' };
        case 'long_term_model':
            return { href: `${base}?view=modelo`, label: 'Genera el modelo' };
        default:
            return null;
    }
}

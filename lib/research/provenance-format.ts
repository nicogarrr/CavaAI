/**
 * Fichas «etiqueta / valor» para los inputs inferidos de una tesis (F4).
 * Antes salian claves crudas (addressable_subscribers) y decimales largos
 * (0.1442999). Aqui: etiqueta en español y valor formateado, con un unico
 * criterio: dinero en dolares estilo ingles ($4.87B), porcentajes con coma
 * (14,4 %), cantidades con separador de miles.
 * Sin imports a proposito: se prueba con node --experimental-strip-types.
 */

const PERCENT_HINT = /(pct|percent|margin|penetration|utilization|share|rate|growth|yield|wacc|cagr|tax|churn|mix)/i;
const MONEY_HINT = /(price|arpu|revenue|ingresos|fcf|capex|debt|cash|cap$|market_cap|value|valor|ebitda|income|cost|spend|ev$|equity)/i;
const NA = "N/D";

function toNumber(value: number | string | null | undefined): number | null {
    if (value === null || value === undefined || value === "") return null;
    const parsed = typeof value === "number" ? value : Number(String(value).replace(/,/g, ""));
    return Number.isFinite(parsed) ? parsed : null;
}

/** "$4.87B", "$14.40", "-$2.3M": importes en USD con escala inglesa. */
export function formatUsdShort(value: number): string {
    const abs = Math.abs(value);
    return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        notation: abs >= 1e6 ? "compact" : "standard",
        maximumFractionDigits: abs >= 1e6 ? 2 : abs >= 100 ? 0 : 2,
    }).format(value);
}

/** Valor legible de un input de la tesis segun lo que dice su clave. */
export function formatProvenanceValue(key: string, value: number | string | null | undefined): string {
    const parsed = toNumber(value);
    if (parsed === null) {
        if (typeof value === "string" && value.trim() !== "") return value.trim();
        return NA;
    }
    if (PERCENT_HINT.test(key)) {
        const ratio = Math.abs(parsed) <= 1 ? parsed : parsed / 100;
        return new Intl.NumberFormat("es-ES", {
            style: "percent",
            minimumFractionDigits: 1,
            maximumFractionDigits: 1,
        }).format(ratio);
    }
    if (MONEY_HINT.test(key)) return formatUsdShort(parsed);
    return new Intl.NumberFormat("es-ES", {
        notation: Math.abs(parsed) >= 1e6 ? "compact" : "standard",
        maximumFractionDigits: 2,
    }).format(parsed);
}

/** "addressable_subscribers" -> "Suscriptores direccionables" (primera letra en mayuscula). */
export function capitalizeLabel(label: string): string {
    const clean = label.trim();
    return clean ? clean.charAt(0).toUpperCase() + clean.slice(1) : clean;
}

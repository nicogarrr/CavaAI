/**
 * Validadores ProPicks: anti-datos-futuros y anti-alucinación.
 *
 * Módulo puro (sin imports, sin I/O): puede ejecutarse tanto en el servidor
 * como en el test `scripts/propicks-guard.test.ts` con node --experimental-strip-types.
 *
 * Reglas:
 *  - R1 (as_of): todo pick declara `asOf` (ISO) <= ahora. Ningún cálculo puede
 *    usar datos con timestamp posterior al corte.
 *  - R2 (trazabilidad): cada motivo de confianza referencia `metric`, esa clave
 *    existe en `facts` y el valor coincide (tolerancia numérica). Además el texto
 *    del motivo contiene el valor, para que lo mostrado sea verificable.
 *  - R3 (números mostrados): currentPrice/targetPrice/upsidePotential son
 *    coherentes con `facts` (upside = (target-price)/price*100 ± 0.5).
 *  - R4 (score): el score general reproduce la fórmula documentada en
 *    SCORING_WEIGHTS con tolerancia ±1 (redondeo).
 */

/** Pesos canónicos del scoring general. Debe coincidir con SCORING_WEIGHTS. */
export const PROPICKS_SCORING_WEIGHTS = {
    value: 0.15,
    growth: 0.20,
    profitability: 0.25,
    cashFlow: 0.15,
    momentum: 0.10,
    debtLiquidity: 0.15,
} as const;

export interface ConfidenceReasonLike {
    text: string;
    metric: string;
    value: number | string;
}

export interface PickLike {
    symbol: string;
    asOf: string;
    facts: Record<string, number | string>;
    confidenceReasons: ConfidenceReasonLike[];
    currentPrice?: number;
    targetPrice?: number;
    upsidePotential?: number;
    score: number;
    categoryScores: Record<string, number>;
}

export interface PickIssue {
    symbol: string;
    rule: 'R1-as_of' | 'R2-trazabilidad' | 'R3-numeros' | 'R4-score';
    message: string;
}

const SKEW_MS = 5 * 60 * 1000; // tolerancia de reloj

function sameValue(fact: number | string, value: number | string): boolean {
    if (typeof fact === 'string' || typeof value === 'string') {
        return String(fact) === String(value);
    }
    return Math.abs(fact - value) <= 0.51;
}

/** R1: el corte temporal es válido y no está en el futuro. */
export function validateNoFutureData(pick: PickLike, now: Date = new Date()): PickIssue[] {
    const issues: PickIssue[] = [];
    if (!pick.asOf) {
        issues.push({ symbol: pick.symbol, rule: 'R1-as_of', message: 'falta asOf: el pick no declara su corte temporal' });
        return issues;
    }
    const asOf = new Date(pick.asOf);
    if (Number.isNaN(asOf.getTime())) {
        issues.push({ symbol: pick.symbol, rule: 'R1-as_of', message: `asOf inválido: ${pick.asOf}` });
        return issues;
    }
    if (asOf.getTime() > now.getTime() + SKEW_MS) {
        issues.push({
            symbol: pick.symbol,
            rule: 'R1-as_of',
            message: `asOf (${pick.asOf}) posterior a ahora: posible uso de datos futuros`,
        });
    }
    return issues;
}

/** R2: cada motivo de confianza es trazable a facts. */
export function validateReasonsTraceable(pick: PickLike): PickIssue[] {
    const issues: PickIssue[] = [];
    if (!Array.isArray(pick.confidenceReasons) || pick.confidenceReasons.length < 2) {
        issues.push({
            symbol: pick.symbol,
            rule: 'R2-trazabilidad',
            message: 'se exigen al menos 2 motivos de confianza trazables por pick',
        });
        return issues;
    }
    for (const reason of pick.confidenceReasons) {
        if (!(reason.metric in pick.facts)) {
            issues.push({
                symbol: pick.symbol,
                rule: 'R2-trazabilidad',
                message: `motivo "${reason.text}" referencia "${reason.metric}", ausente en facts: número no verificable`,
            });
            continue;
        }
        if (!sameValue(pick.facts[reason.metric], reason.value)) {
            issues.push({
                symbol: pick.symbol,
                rule: 'R2-trazabilidad',
                message: `motivo "${reason.text}": valor ${reason.value} ≠ facts.${reason.metric} (${pick.facts[reason.metric]})`,
            });
        }
        if (!reason.text.includes(String(reason.value))) {
            issues.push({
                symbol: pick.symbol,
                rule: 'R2-trazabilidad',
                message: `motivo "${reason.text}" no muestra su valor (${reason.value}): no es verificable en UI`,
            });
        }
    }
    return issues;
}

/** R3: los números mostrados derivan de facts/quotes. */
export function validateNumbersTraceable(pick: PickLike): PickIssue[] {
    const issues: PickIssue[] = [];
    const price = pick.facts['price'];
    if (pick.currentPrice !== undefined && pick.currentPrice > 0) {
        if (typeof price !== 'number' || Math.abs(pick.currentPrice - price) > Math.max(0.5, price * 0.02)) {
            issues.push({
                symbol: pick.symbol,
                rule: 'R3-numeros',
                message: `currentPrice (${pick.currentPrice}) no coincide con facts.price (${price})`,
            });
        }
    }
    const target = pick.facts['targetMean'];
    if (pick.targetPrice !== undefined && pick.targetPrice > 0) {
        if (typeof target !== 'number' || Math.abs(pick.targetPrice - target) > Math.max(0.5, target * 0.02)) {
            issues.push({
                symbol: pick.symbol,
                rule: 'R3-numeros',
                message: `targetPrice (${pick.targetPrice}) no coincide con facts.targetMean (${target})`,
            });
        }
    }
    if (
        pick.upsidePotential !== undefined &&
        pick.currentPrice !== undefined && pick.currentPrice > 0 &&
        pick.targetPrice !== undefined && pick.targetPrice > 0
    ) {
        const expected = ((pick.targetPrice - pick.currentPrice) / pick.currentPrice) * 100;
        if (Math.abs(pick.upsidePotential - expected) > 0.5) {
            issues.push({
                symbol: pick.symbol,
                rule: 'R3-numeros',
                message: `upsidePotential (${pick.upsidePotential}) ≠ calculado (${expected.toFixed(2)})`,
            });
        }
    }
    return issues;
}

/** R4: el score reproduce la fórmula documentada (pesos canónicos, ±1 por redondeo). */
export function validateScoreFormula(pick: PickLike): PickIssue[] {
    const w = PROPICKS_SCORING_WEIGHTS;
    const c = pick.categoryScores;
    const keys = Object.keys(w) as Array<keyof typeof w>;
    for (const key of keys) {
        if (typeof c[key] !== 'number' || !Number.isFinite(c[key])) {
            return [{ symbol: pick.symbol, rule: 'R4-score', message: `categoría "${key}" sin puntuación numérica` }];
        }
    }
    const expected = Math.round(keys.reduce((sum, key) => sum + c[key] * w[key], 0));
    if (Math.abs(pick.score - expected) > 1) {
        return [{
            symbol: pick.symbol,
            rule: 'R4-score',
            message: `score (${pick.score}) ≠ fórmula documentada (${expected}): pesos o cálculo divergentes`,
        }];
    }
    return [];
}

/** Ejecuta las 4 reglas sobre una lista de picks. Vacío = todo válido. */
export function validatePicks(picks: PickLike[], now: Date = new Date()): PickIssue[] {
    return picks.flatMap((pick) => [
        ...validateNoFutureData(pick, now),
        ...validateReasonsTraceable(pick),
        ...validateNumbersTraceable(pick),
        ...validateScoreFormula(pick),
    ]);
}

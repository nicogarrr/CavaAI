import type { ProPick } from '@/lib/actions/proPicks.actions';

/**
 * F184: puntuación visible de una categoría del pick. El embudo v1 pondera
 * seis categorías, pero las que no tienen datos para todo el universo caen a
 * 50 neutral (marcadas en `facts` con su flag `*_neutral_sin_datos`, y la
 * deuda de bancos con `deuda_neutral_banco`): un «50» pelado se leía como un
 * score real. Regla: categoría neutral -> se muestra n/d, nunca el 50;
 * categoría con datos -> su score real.
 */
export type CategoryKey = 'value' | 'growth' | 'profitability' | 'cashFlow' | 'momentum' | 'debtLiquidity';

const NEUTRAL_FACT_FLAGS: Record<CategoryKey, string[]> = {
    value: ['valoracion_neutral_sin_datos'],
    growth: ['crecimiento_neutral_sin_datos'],
    profitability: ['moat_neutral_sin_datos'],
    cashFlow: ['fcf_neutral_sin_datos'],
    momentum: ['momentum_neutral_sin_datos'],
    debtLiquidity: ['deuda_neutral_sin_datos', 'deuda_neutral_banco'],
};

export type CategoryDisplay = { kind: 'score'; value: number } | { kind: 'neutral' };

export function categoryDisplay(pick: ProPick, key: CategoryKey): CategoryDisplay {
    const flags = NEUTRAL_FACT_FLAGS[key];
    if (flags.some((flag) => pick.facts?.[flag] === 'si')) {
        return { kind: 'neutral' };
    }
    return { kind: 'score', value: pick.categoryScores[key] };
}

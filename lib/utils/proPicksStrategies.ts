/**
 * Estrategias ProPicks - Similar a Investing Pro
 * 
 * Cada estrategia aplica filtros específicos usando el modelo de scoring avanzado
 */

import { AdvancedScoreData } from './advancedStockScoring';

export interface ProPickStrategy {
    id: string;
    name: string;
    description: string;
    categoryWeights: {
        value: number;
        growth: number;
        profitability: number;
        cashFlow: number;
        momentum: number;
        debtLiquidity: number;
    };
    filters: {
        minScore?: number;
        minCategoryScores?: Partial<AdvancedScoreData['categoryScores']>;
        sectors?: string[];
        maxPrice?: number;
        minMarketCap?: number;
    };
}

/**
 * Estrategia única adaptativa - La IA selecciona las mejores acciones según datos reales actuales
 */
export const PROPICKS_STRATEGIES: ProPickStrategy[] = [
    {
        id: 'adaptive',
        name: 'Selección Adaptativa IA',
        description: 'La IA analiza datos reales actuales del mercado y selecciona las mejores oportunidades en cada momento',
        categoryWeights: {
            value: 0.20,
            growth: 0.20,
            profitability: 0.20,
            cashFlow: 0.15,
            momentum: 0.15,
            debtLiquidity: 0.10,
        },
        filters: {
            // Sin filtros estrictos - la IA decide basándose en datos reales
            minScore: 60,
        },
    },
];

/**
 * Obtiene una estrategia por ID
 */
export function getStrategyById(id: string): ProPickStrategy | undefined {
    return PROPICKS_STRATEGIES.find(s => s.id === id);
}

/**
 * Calcula score ponderado según estrategia
 */
export function calculateStrategyScore(
    advancedScore: AdvancedScoreData,
    strategy: ProPickStrategy
): number {
    const { categoryScores } = advancedScore;
    const { categoryWeights } = strategy;

    return Math.round(
        categoryScores.value * categoryWeights.value +
        categoryScores.growth * categoryWeights.growth +
        categoryScores.profitability * categoryWeights.profitability +
        categoryScores.cashFlow * categoryWeights.cashFlow +
        categoryScores.momentum * categoryWeights.momentum +
        categoryScores.debtLiquidity * categoryWeights.debtLiquidity
    );
}

/**
 * Verifica si una acción pasa los filtros de una estrategia
 */
export function passesStrategyFilters(
    advancedScore: AdvancedScoreData,
    strategy: ProPickStrategy,
    sector?: string,
    price?: number,
    marketCap?: number
): boolean {
    const { filters } = strategy;

    // Verificar score mínimo
    if (filters.minScore && advancedScore.overallScore < filters.minScore) {
        return false;
    }

    // Verificar scores mínimos por categoría
    if (filters.minCategoryScores) {
        for (const [category, minScore] of Object.entries(filters.minCategoryScores)) {
            if (advancedScore.categoryScores[category as keyof typeof advancedScore.categoryScores] < minScore!) {
                return false;
            }
        }
    }

    // Verificar sector
    if (filters.sectors && sector && !filters.sectors.includes(sector)) {
        return false;
    }

    // Verificar precio máximo
    if (filters.maxPrice && price && price > filters.maxPrice) {
        return false;
    }

    // Verificar market cap mínimo
    if (filters.minMarketCap && marketCap && marketCap < filters.minMarketCap) {
        return false;
    }

    return true;
}


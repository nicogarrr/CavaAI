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
 * Estrategias predefinidas similares a Investing Pro
 */
export const PROPICKS_STRATEGIES: ProPickStrategy[] = [
    {
        id: 'beat-sp500',
        name: 'Batir al S&P 500',
        description: 'Selecciona las mejores acciones del S&P 500 con alta salud financiera y valor relativo',
        categoryWeights: {
            value: 0.20,
            growth: 0.15,
            profitability: 0.25,
            cashFlow: 0.15,
            momentum: 0.15,
            debtLiquidity: 0.10,
        },
        filters: {
            minScore: 75,
            minCategoryScores: {
                profitability: 70,
                value: 65,
            },
        },
    },
    {
        id: 'tech-titans',
        name: 'Titanes Tecnológicos',
        description: 'Acciones tecnológicas con fuerte crecimiento e impulso',
        categoryWeights: {
            value: 0.10,
            growth: 0.30,
            profitability: 0.20,
            cashFlow: 0.15,
            momentum: 0.20,
            debtLiquidity: 0.05,
        },
        filters: {
            minScore: 70,
            sectors: ['Technology', 'Software', 'Semiconductors'],
            minCategoryScores: {
                growth: 75,
                momentum: 70,
            },
        },
    },
    {
        id: 'buffett-style',
        name: 'Estilo Buffett',
        description: 'Modela los principios de Warren Buffett: alta rentabilidad, poca deuda, buen valor',
        categoryWeights: {
            value: 0.25,
            growth: 0.10,
            profitability: 0.35,
            cashFlow: 0.20,
            momentum: 0.05,
            debtLiquidity: 0.15,
        },
        filters: {
            minScore: 80,
            minCategoryScores: {
                profitability: 80,
                debtLiquidity: 75,
                value: 70,
            },
        },
    },
    {
        id: 'growth-champions',
        name: 'Campeones del Crecimiento',
        description: 'Acciones con crecimiento excepcional de ingresos y beneficios',
        categoryWeights: {
            value: 0.10,
            growth: 0.40,
            profitability: 0.20,
            cashFlow: 0.15,
            momentum: 0.10,
            debtLiquidity: 0.05,
        },
        filters: {
            minScore: 75,
            minCategoryScores: {
                growth: 80,
                profitability: 70,
            },
        },
    },
    {
        id: 'value-gems',
        name: 'Joyas de Valor',
        description: 'Acciones infravaloradas con fundamentos sólidos',
        categoryWeights: {
            value: 0.40,
            growth: 0.10,
            profitability: 0.20,
            cashFlow: 0.15,
            momentum: 0.10,
            debtLiquidity: 0.05,
        },
        filters: {
            minScore: 70,
            minCategoryScores: {
                value: 80,
                profitability: 65,
            },
        },
    },
    {
        id: 'dividend-aristocrats',
        name: 'Aristócratas del Dividendo',
        description: 'Acciones estables con alto flujo de caja y rentabilidad consistente',
        categoryWeights: {
            value: 0.15,
            growth: 0.10,
            profitability: 0.25,
            cashFlow: 0.30,
            momentum: 0.10,
            debtLiquidity: 0.10,
        },
        filters: {
            minScore: 75,
            minCategoryScores: {
                cashFlow: 75,
                profitability: 75,
                debtLiquidity: 70,
            },
        },
    },
    {
        id: 'undervalued-gems',
        name: 'Joyas Infravaloradas',
        description: 'Acciones con excelente valor relativo y fundamentos sólidos',
        categoryWeights: {
            value: 0.45,
            growth: 0.15,
            profitability: 0.20,
            cashFlow: 0.10,
            momentum: 0.05,
            debtLiquidity: 0.05,
        },
        filters: {
            minScore: 70,
            minCategoryScores: {
                value: 85,
                profitability: 65,
            },
        },
    },
    {
        id: 'momentum-leaders',
        name: 'Líderes del Impulso',
        description: 'Acciones con fuerte momentum de precio y tendencia alcista',
        categoryWeights: {
            value: 0.05,
            growth: 0.20,
            profitability: 0.15,
            cashFlow: 0.10,
            momentum: 0.40,
            debtLiquidity: 0.10,
        },
        filters: {
            minScore: 70,
            minCategoryScores: {
                momentum: 80,
                growth: 65,
            },
        },
    },
    {
        id: 'cash-rich',
        name: 'Ricas en Efectivo',
        description: 'Empresas con flujo de caja libre excepcional y balance sólido',
        categoryWeights: {
            value: 0.10,
            growth: 0.15,
            profitability: 0.20,
            cashFlow: 0.40,
            momentum: 0.10,
            debtLiquidity: 0.05,
        },
        filters: {
            minScore: 75,
            minCategoryScores: {
                cashFlow: 85,
                debtLiquidity: 75,
            },
        },
    },
    {
        id: 'recovery-plays',
        name: 'Jugadas de Recuperación',
        description: 'Acciones que están recuperándose con fundamentos mejorando',
        categoryWeights: {
            value: 0.20,
            growth: 0.25,
            profitability: 0.20,
            cashFlow: 0.15,
            momentum: 0.15,
            debtLiquidity: 0.05,
        },
        filters: {
            minScore: 65,
            minCategoryScores: {
                growth: 70,
                momentum: 60,
            },
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


'use server';

import { getStockFinancialData, getCandles } from './finnhub.actions';
import { calculateAdvancedStockScore } from '@/lib/utils/advancedStockScoring';
import { 
    PROPICKS_STRATEGIES, 
    calculateStrategyScore, 
    passesStrategyFilters,
    type ProPickStrategy 
} from '@/lib/utils/proPicksStrategies';

export interface ProPick {
    symbol: string;
    company: string;
    score: number;
    grade: string;
    strategyScore?: number; // Score según estrategia específica
    strategy?: string; // ID de la estrategia aplicada
    categoryScores: {
        value: number;
        growth: number;
        profitability: number;
        cashFlow: number;
        momentum: number;
        debtLiquidity: number;
    };
    reasons: string[];
    currentPrice: number;
    sector?: string;
    exchange?: string;
    vsSector?: {
        value: number;
        growth: number;
        profitability: number;
        cashFlow: number;
        momentum: number;
        debtLiquidity: number;
    };
}

/**
 * ProPicks IA Mejorado - Similar a Investing Pro
 * 
 * Características:
 * - Comparación con sector (crucial)
 * - Múltiples categorías de métricas
 * - Estrategias predefinidas
 * - Scoring avanzado
 */
export async function generateProPicks(
    limit: number = 10,
    strategyId?: string
): Promise<ProPick[]> {
    try {
        // Seleccionar estrategia o usar estrategia por defecto
        const strategy = strategyId 
            ? PROPICKS_STRATEGIES.find(s => s.id === strategyId)
            : PROPICKS_STRATEGIES[0]; // 'beat-sp500' por defecto

        if (!strategy) {
            throw new Error(`Estrategia no encontrada: ${strategyId}`);
        }

        // Universo de acciones más amplio (S&P 500 aproximado) - Expandido para mejor diversificación
        const universeSymbols = [
            // Technology (18)
            'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'META', 'TSLA', 'AMD', 'INTC', 'CRM', 
            'AVGO', 'QCOM', 'TXN', 'ADBE', 'ORCL', 'NOW', 'SNOW',
            // Financials (12)
            'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'V', 'MA', 'PYPL', 'AXP', 'COF', 'SCHW',
            // Healthcare (15)
            'JNJ', 'PFE', 'UNH', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT', 'DHR', 'ISRG', 'CI', 
            'CVS', 'ELV', 'HCA', 'ZTS',
            // Consumer Discretionary (12)
            'WMT', 'HD', 'NKE', 'MCD', 'SBUX', 'DIS', 'NFLX', 'TJX', 'LOW', 'TGT', 'NKE', 'BKNG',
            // Consumer Staples (10)
            'PG', 'KO', 'PEP', 'WMT', 'COST', 'PM', 'MO', 'CL', 'EL', 'CLX',
            // Industrial (12)
            'BA', 'CAT', 'GE', 'HON', 'UNP', 'RTX', 'ETN', 'EMR', 'CMI', 'ITW', 'DE', 'PH',
            // Energy (8)
            'XOM', 'CVX', 'COP', 'SLB', 'MPC', 'VLO', 'PSX', 'EOG',
            // Communication (6)
            'VZ', 'T', 'CMCSA', 'DIS', 'NFLX', 'META',
            // Utilities (5)
            'NEE', 'DUK', 'SO', 'D', 'AEP',
            // Materials (6)
            'LIN', 'APD', 'ECL', 'SHW', 'PPG', 'FCX',
            // Real Estate (5)
            'AMT', 'PLD', 'EQIX', 'PSA', 'WELL',
            // Others (3)
            'TSM', 'ASML', 'BABA',
        ];

        const picks: ProPick[] = [];
        // Evaluar más símbolos para tener mejor diversificación sectorial
        const maxSymbols = Math.min(60, universeSymbols.length); // Aumentado de 30 a 60

        // Contenedor para todas las acciones evaluadas (incluso si no pasan filtros)
        const allEvaluatedPicks: ProPick[] = [];
        
        // Mapa para tracking de sectores en picks finales (para diversificación)
        const sectorCount: Map<string, number> = new Map();
        
        // Evaluar cada acción secuencialmente
        for (let i = 0; i < maxSymbols && (picks.length < limit * 3 || allEvaluatedPicks.length < limit * 4); i++) {
            const symbol = universeSymbols[i];
            
            try {
                // Obtener datos financieros
                const financialData = await getStockFinancialData(symbol);
                
                if (!financialData || !financialData.profile) {
                    await new Promise(resolve => setTimeout(resolve, 500));
                    continue;
                }

                const sector = financialData.profile.finnhubIndustry || 'Unknown';
                const currentPrice = financialData.quote?.c || financialData.quote?.price || 0;
                const marketCap = financialData.profile.marketCapitalization || 0;

                // Obtener datos históricos para momentum (si es posible, sino usar quote)
                let historicalData;
                try {
                    const to = Math.floor(Date.now() / 1000);
                    const from = to - (365 * 24 * 60 * 60); // 1 año
                    const candles = await getCandles(symbol, from, to, 'D', 3600);
                    if (candles.s === 'ok' && candles.c.length > 0) {
                        historicalData = {
                            prices: candles.c,
                            dates: candles.t,
                        };
                    }
                } catch (e) {
                    // Si falla, continuar sin datos históricos
                }

                // Calcular score avanzado (con comparación sectorial)
                const advancedScore = await calculateAdvancedStockScore(
                    financialData, 
                    historicalData || undefined
                );

                // Calcular score según estrategia
                const strategyScore = calculateStrategyScore(advancedScore, strategy);

                // Combinar razones
                const allReasons = [
                    ...advancedScore.reasons.strengths,
                    ...advancedScore.reasons.opportunities,
                ].slice(0, 5);

                const pick: ProPick = {
                    symbol,
                    company: financialData.profile.name || symbol,
                    score: advancedScore.overallScore,
                    grade: advancedScore.grade,
                    strategyScore,
                    strategy: strategy.id,
                    categoryScores: advancedScore.categoryScores,
                    reasons: allReasons.length > 0 ? allReasons : [
                        'Fundamentos sólidos',
                        'Buena salud financiera',
                        'Potencial de crecimiento',
                    ],
                    currentPrice,
                    sector,
                    exchange: financialData.profile.exchange || undefined,
                    vsSector: advancedScore.sectorComparison?.vsSector,
                };

                // Guardar todos los picks evaluados
                allEvaluatedPicks.push(pick);

                // Si pasa los filtros de la estrategia, agregarlo a picks
                if (passesStrategyFilters(advancedScore, strategy, sector, currentPrice, marketCap)) {
                    picks.push(pick);
                }

                // Delay reducido entre requests
                await new Promise(resolve => setTimeout(resolve, 500));
            } catch (error: any) {
                // Si es error 429, parar completamente
                if (error?.message?.includes('429') || error?.message?.includes('limit')) {
                    console.warn(`Rate limit reached, stopping at ${picks.length} picks`);
                    break;
                }
                console.error(`Error evaluating ${symbol}:`, error);
                await new Promise(resolve => setTimeout(resolve, 500));
                continue;
            }

            // Si ya tenemos suficientes picks de calidad, podemos parar antes
            if (picks.length >= limit * 1.5) {
                break;
            }
        }

        // Si tenemos picks que pasaron los filtros, aplicar diversificación sectorial
        if (picks.length > 0) {
            // Función para calcular score de diversificación (prioriza sectores menos representados)
            const getDiversificationScore = (pick: ProPick, currentSectorCount: Map<string, number>): number => {
                const sector = pick.sector || 'Unknown';
                const currentCount = currentSectorCount.get(sector) || 0;
                // Penalizar sectores ya representados (máximo 2-3 picks por sector)
                const sectorPenalty = Math.min(currentCount * 5, 15); // Máximo 15 puntos de penalización
                
                // Bonus por comparación con sector (si está disponible)
                const vsSectorBonus = pick.vsSector 
                    ? (pick.vsSector.value + pick.vsSector.profitability + pick.vsSector.growth) / 30
                    : 0;
                
                return (pick.strategyScore ?? pick.score) - sectorPenalty + vsSectorBonus;
            };

            // Ordenar picks considerando diversificación sectorial
            const diversifiedPicks: ProPick[] = [];
            const usedSectors = new Map<string, number>();
            const remainingPicks = [...picks];

            // Primera pasada: seleccionar el mejor pick de cada sector principal
            const sectorGroups = new Map<string, ProPick[]>();
            remainingPicks.forEach(pick => {
                const sector = pick.sector || 'Unknown';
                if (!sectorGroups.has(sector)) {
                    sectorGroups.set(sector, []);
                }
                sectorGroups.get(sector)!.push(pick);
            });

            // Seleccionar top picks de cada sector (hasta 2 por sector)
            sectorGroups.forEach((sectorPicks, sector) => {
                const sorted = sectorPicks.sort((a, b) => {
                    const scoreA = a.strategyScore ?? a.score;
                    const scoreB = b.strategyScore ?? b.score;
                    return scoreB - scoreA;
                });
                // Tomar hasta 2 del mismo sector
                const topPicks = sorted.slice(0, 2);
                topPicks.forEach(pick => {
                    diversifiedPicks.push(pick);
                    usedSectors.set(sector, (usedSectors.get(sector) || 0) + 1);
                });
            });

            // Si aún no tenemos suficientes picks, completar con los mejores restantes
            if (diversifiedPicks.length < limit) {
                const remaining = remainingPicks
                    .filter(p => !diversifiedPicks.includes(p))
                    .sort((a, b) => {
                        const divScoreA = getDiversificationScore(a, usedSectors);
                        const divScoreB = getDiversificationScore(b, usedSectors);
                        return divScoreB - divScoreA;
                    });

                const needed = limit - diversifiedPicks.length;
                for (let i = 0; i < needed && i < remaining.length; i++) {
                    const pick = remaining[i];
                    diversifiedPicks.push(pick);
                    const sector = pick.sector || 'Unknown';
                    usedSectors.set(sector, (usedSectors.get(sector) || 0) + 1);
                }
            }

            // Ordenar final por strategyScore (los que quedaron después de diversificación)
            const sortedPicks = diversifiedPicks.sort((a, b) => {
                const scoreA = a.strategyScore ?? a.score;
                const scoreB = b.strategyScore ?? b.score;
                return scoreB - scoreA;
            });

            return sortedPicks.slice(0, limit);
        }

        // Si no hay picks que pasaron los filtros, usar los mejores evaluados
        // (Estrategia de fallback para asegurar que siempre hay picks)
        if (allEvaluatedPicks.length > 0) {
            console.warn(`No se encontraron picks que pasen todos los filtros, usando los mejores evaluados`);
            
            // Ordenar todos los picks evaluados por strategyScore o overallScore
            const sortedAllPicks = allEvaluatedPicks.sort((a, b) => {
                const scoreA = a.strategyScore ?? a.score;
                const scoreB = b.strategyScore ?? b.score;
                return scoreB - scoreA;
            });

            // Retornar los mejores aunque no pasen todos los filtros
            return sortedAllPicks.slice(0, limit);
        }

        // Si no hay picks en absoluto, retornar array vacío
        return [];
    } catch (error) {
        console.error('Error generating ProPicks:', error);
        // Si no hay datos disponibles, devolver array vacío
        // Los componentes UI mostrarán mensaje apropiado
        return [];
    }
}

/**
 * Genera ProPicks para una estrategia específica
 */
export async function generateProPicksForStrategy(
    strategyId: string,
    limit: number = 10
): Promise<ProPick[]> {
    return generateProPicks(limit, strategyId);
}

/**
 * Obtiene todas las estrategias disponibles
 */
export async function getAvailableStrategies() {
    return PROPICKS_STRATEGIES.map(s => ({
        id: s.id,
        name: s.name,
        description: s.description,
    }));
}

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

        // Universo de acciones más amplio (S&P 500 aproximado)
        const universeSymbols = [
            // Tech
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AMD', 'INTC', 'CRM',
            // Financials
            'JPM', 'BAC', 'WFC', 'GS', 'V', 'MA',
            // Healthcare
            'JNJ', 'PFE', 'UNH', 'ABBV', 'MRK',
            // Consumer
            'WMT', 'HD', 'NKE', 'MCD', 'SBUX', 'DIS', 'NFLX',
            // Industrial
            'BA', 'CAT', 'GE', 'HON',
            // Energy
            'XOM', 'CVX', 'COP',
            // Others
            'PG', 'KO', 'PEP', 'TMO', 'AVGO', 'QCOM', 'TXN',
        ];

        const picks: ProPick[] = [];
        const maxSymbols = Math.min(30, universeSymbols.length); // Evaluar hasta 30 para tener opciones

        // Evaluar cada acción secuencialmente
        for (let i = 0; i < maxSymbols && picks.length < limit * 2; i++) {
            const symbol = universeSymbols[i];
            
            try {
                // Obtener datos financieros
                const financialData = await getStockFinancialData(symbol);
                
                if (!financialData || !financialData.profile) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
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

                // Verificar si pasa los filtros de la estrategia
                if (!passesStrategyFilters(advancedScore, strategy, sector, currentPrice, marketCap)) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    continue;
                }

                // Calcular score según estrategia
                const strategyScore = calculateStrategyScore(advancedScore, strategy);

                // Combinar razones
                const allReasons = [
                    ...advancedScore.reasons.strengths,
                    ...advancedScore.reasons.opportunities,
                ].slice(0, 5);

                picks.push({
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
                });

                // Delay entre requests
                await new Promise(resolve => setTimeout(resolve, 1000));
            } catch (error: any) {
                // Si es error 429, parar completamente
                if (error?.message?.includes('429') || error?.message?.includes('limit')) {
                    console.warn(`Rate limit reached, stopping at ${picks.length} picks`);
                    break;
                }
                console.error(`Error evaluating ${symbol}:`, error);
                await new Promise(resolve => setTimeout(resolve, 1000));
                continue;
            }

            // Si ya tenemos suficientes picks de calidad, podemos parar antes
            if (picks.length >= limit * 1.5) {
                break;
            }
        }

        // Ordenar por strategyScore (si está disponible) o por overallScore
        const sortedPicks = picks.sort((a, b) => {
            const scoreA = a.strategyScore ?? a.score;
            const scoreB = b.strategyScore ?? b.score;
            return scoreB - scoreA;
        });

        return sortedPicks.slice(0, limit);
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

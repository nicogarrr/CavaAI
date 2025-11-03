'use server';

import { getStockFinancialData } from './finnhub.actions';
import { calculateHealthScore, HealthScoreData } from '@/lib/utils/healthScore';
import { estimateHealthScoreWithAI } from './ai.actions';

export async function getStockHealthScore(symbol: string): Promise<HealthScoreData | null> {
    try {
        const financialData = await getStockFinancialData(symbol);
        if (!financialData) return null;

        // Calcular Health Score con datos reales
        const healthScore = calculateHealthScore(financialData);

        // Detectar TODAS las categorías faltantes (score 0 indica que no hay datos reales)
        const missingCategories: string[] = [];
        
        if (healthScore.breakdown.profitability === 0) {
            missingCategories.push('profitability');
        }
        
        if (healthScore.breakdown.growth === 0) {
            missingCategories.push('growth');
        }
        
        if (healthScore.breakdown.stability === 0) {
            missingCategories.push('stability');
        }
        
        if (healthScore.breakdown.efficiency === 0) {
            missingCategories.push('efficiency');
        }
        
        if (healthScore.breakdown.valuation === 0) {
            missingCategories.push('valuation');
        }

        // Si faltan categorías, usar IA para estimarlas basándose en todos los datos disponibles
        if (missingCategories.length > 0) {
            try {
                const companyName = financialData.profile?.name || financialData.profile?.ticker || symbol;
                const aiEstimates = await estimateHealthScoreWithAI(
                    symbol,
                    companyName,
                    financialData,
                    missingCategories
                );

                // Aplicar todas las estimaciones de IA y recalcular score total
                if (aiEstimates.profitability !== undefined) {
                    healthScore.breakdown.profitability = aiEstimates.profitability;
                }
                
                if (aiEstimates.growth !== undefined) {
                    healthScore.breakdown.growth = aiEstimates.growth;
                }
                
                if (aiEstimates.stability !== undefined) {
                    healthScore.breakdown.stability = aiEstimates.stability;
                }
                
                if (aiEstimates.efficiency !== undefined) {
                    healthScore.breakdown.efficiency = aiEstimates.efficiency;
                }
                
                if (aiEstimates.valuation !== undefined) {
                    healthScore.breakdown.valuation = aiEstimates.valuation;
                }

                // Recalcular score total con todas las categorías actualizadas
                const totalScore = Math.min(100, Math.round(
                    (healthScore.breakdown.profitability * 0.25) +
                    (healthScore.breakdown.growth * 0.20) +
                    (healthScore.breakdown.stability * 0.25) +
                    (healthScore.breakdown.efficiency * 0.15) +
                    (healthScore.breakdown.valuation * 0.15)
                ));
                healthScore.score = totalScore;
                
                // Actualizar grade
                const { getGrade } = await import('@/lib/utils/healthScore');
                healthScore.grade = getGrade(totalScore);
            } catch (aiError) {
                console.warn('Error estimating Health Score with AI:', aiError);
                // Continuar con scores calculados sin IA
            }
        }

        return healthScore;
    } catch (error) {
        console.error('Error calculating health score:', error);
        return null;
    }
}


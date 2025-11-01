'use server';

import { getStockFinancialData } from './finnhub.actions';
import { calculateHealthScore, HealthScoreData } from '@/lib/utils/healthScore';

export async function getStockHealthScore(symbol: string): Promise<HealthScoreData | null> {
    try {
        const financialData = await getStockFinancialData(symbol);
        if (!financialData) return null;

        return calculateHealthScore(financialData);
    } catch (error) {
        console.error('Error calculating health score:', error);
        return null;
    }
}


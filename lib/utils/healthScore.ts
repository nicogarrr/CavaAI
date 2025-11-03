/**
 * Calcula el Health Score (puntuación de salud financiera) de una acción
 * Basado en múltiples métricas financieras de Finnhub
 */

export interface HealthScoreData {
    score: number; // 0-100
    grade: 'A+' | 'A' | 'A-' | 'B+' | 'B' | 'B-' | 'C+' | 'C' | 'C-' | 'D' | 'F';
    breakdown: {
        profitability: number;
        growth: number;
        stability: number;
        efficiency: number;
        valuation: number;
    };
    strengths: string[];
    weaknesses: string[];
}

export function calculateHealthScore(financialData: any): HealthScoreData {
    const scores = {
        profitability: 0,
        growth: 0,
        stability: 0,
        efficiency: 0,
        valuation: 0,
    };

    const strengths: string[] = [];
    const weaknesses: string[] = [];

    // Acceder a métricas - Finnhub devuelve diferentes estructuras
    const metrics = financialData.metrics?.metric || financialData.metrics || {};
    const profile = financialData.profile || {};
    const quote = financialData.quote || {};

    // Helper para obtener valores numéricos de diferentes formatos
    const getNumeric = (value: any): number | null => {
        if (value === null || value === undefined || value === '') return null;
        const num = typeof value === 'string' ? parseFloat(value.replace(/,/g, '')) : Number(value);
        return isNaN(num) ? null : num;
    };

    // Helper para buscar métricas con diferentes nombres posibles
    const getMetric = (...names: string[]): number | null => {
        for (const name of names) {
            const value = getNumeric(metrics[name]);
            if (value !== null) return value;
        }
        return null;
    };

    // ========== 1. PROFITABILITY (Rentabilidad) ==========
    // Margen de beneficio neto
    const netMargin = getMetric('netProfitMarginTTM', 'netProfitMargin', 'profitMargin', 'netMargin', 'netProfitMarginAnnual');
    if (netMargin !== null) {
        const margin = Math.abs(netMargin) > 1 ? Math.abs(netMargin) / 100 : Math.abs(netMargin);
        if (margin > 0.2) scores.profitability += 25;
        else if (margin > 0.1) scores.profitability += 20;
        else if (margin > 0.05) scores.profitability += 15;
        else if (margin > 0) scores.profitability += 10;
        
        if (margin > 0.15) strengths.push('Altos márgenes de beneficio');
        else if (netMargin < 0) weaknesses.push('Margen de beneficio negativo');
    }

    // ROE (Return on Equity)
    const roe = getMetric('roeTTM', 'roe', 'returnOnEquity', 'returnOnEquityTTM', 'roeAnnual');
    if (roe !== null) {
        const roeValue = Math.abs(roe) > 1 ? Math.abs(roe) / 100 : Math.abs(roe);
        if (roeValue > 0.2) scores.profitability += 25;
        else if (roeValue > 0.15) scores.profitability += 20;
        else if (roeValue > 0.1) scores.profitability += 15;
        else if (roeValue > 0.05) scores.profitability += 10;
        
        if (roeValue > 0.2) strengths.push('ROE excelente');
        else if (roe < 0) weaknesses.push('ROE negativo');
    }

    // ROA (Return on Assets)
    const roa = getMetric('roaTTM', 'roa', 'returnOnAssets', 'returnOnAssetsTTM', 'roaAnnual');
    if (roa !== null) {
        const roaValue = Math.abs(roa) > 1 ? Math.abs(roa) / 100 : Math.abs(roa);
        if (roaValue > 0.1) scores.profitability += 25;
        else if (roaValue > 0.05) scores.profitability += 20;
        else if (roaValue > 0) scores.profitability += 15;
        
        if (roaValue > 0.1) strengths.push('ROA sólido');
        else if (roa < 0) weaknesses.push('ROA negativo');
    }

    // ========== 2. GROWTH (Crecimiento) ==========
    // Crecimiento de ingresos
    const revenueGrowth = getMetric(
        'revenueGrowthTTM', 
        'revenueGrowth', 
        'revenueGrowth3Year',
        'revenueGrowthAnnual',
        'salesGrowth',
        'yearlyRevenueGrowth',
        'revenueGrowthRate'
    );
    if (revenueGrowth !== null) {
        let growth = revenueGrowth / 100; // Convertir porcentaje a decimal
        if (Math.abs(growth) > 1) growth = growth / 100; // Normalizar si viene en porcentaje doble
        
        if (growth > 0.2) scores.growth += 25;
        else if (growth > 0.1) scores.growth += 20;
        else if (growth > 0.05) scores.growth += 15;
        else if (growth > 0) scores.growth += 10;
        
        if (growth > 0.15) strengths.push('Crecimiento de ingresos fuerte');
        else if (growth < 0) weaknesses.push('Ingresos en declive');
    }

    // Crecimiento de EBITDA
    const ebitdaGrowth = getMetric(
        'ebitdaGrowthTTM',
        'ebitdaGrowth',
        'yearlyEbitdaGrowth',
        'operatingIncomeGrowth',
        'ebitdaGrowthRate'
    );
    if (ebitdaGrowth !== null) {
        let growth = ebitdaGrowth / 100;
        if (Math.abs(growth) > 1) growth = growth / 100;
        
        if (growth > 0.2) scores.growth += 25;
        else if (growth > 0.1) scores.growth += 20;
        else if (growth > 0) scores.growth += 15;
        
        if (growth > 0.15) strengths.push('Crecimiento EBITDA sólido');
        else if (growth < 0) weaknesses.push('EBITDA en declive');
    }

    // Crecimiento de EPS
    const epsGrowth = getMetric('epsGrowth', 'epsGrowthTTM', 'earningsGrowth', 'yearlyEarningsGrowth', 'epsGrowthRate');
    if (epsGrowth !== null) {
        let growth = epsGrowth / 100;
        if (Math.abs(growth) > 1) growth = growth / 100;
        
        if (growth > 0.15) scores.growth += 15;
        else if (growth > 0.1) scores.growth += 12;
        else if (growth > 0) scores.growth += 8;
    }

    // Si no hay métricas de crecimiento y hay quote con cambio, usar estimación
    if (scores.growth === 0 && quote.dp) {
        const priceChange = quote.dp / 100; // Cambio porcentual diario
        const estimatedGrowth = Math.abs(priceChange) * 250; // Estimación anual aproximada
        if (estimatedGrowth > 0.1 && priceChange > 0) {
            scores.growth += 10; // Puntuación mínima si hay crecimiento de precio
        }
    }

    // ========== 3. STABILITY (Estabilidad) ==========
    // Deuda a Capital (Debt to Equity)
    const debtToEquity = getMetric(
        'debtToEquityTTM',
        'debtToEquity',
        'totalDebtToEquity',
        'debtEquityRatio',
        'longTermDebtToEquity'
    );
    if (debtToEquity !== null) {
        const dte = Math.abs(debtToEquity);
        if (dte < 0.5) scores.stability += 30;
        else if (dte < 1) scores.stability += 25;
        else if (dte < 2) scores.stability += 15;
        else if (dte < 3) scores.stability += 10;
        else scores.stability += 5;
        
        if (dte < 0.5) strengths.push('Baja deuda');
        else if (dte > 3) weaknesses.push('Alto endeudamiento');
    }

    // Ratio Corriente (Current Ratio)
    const currentRatio = getMetric(
        'currentRatioTTM',
        'currentRatio',
        'currentAssetsToCurrentLiabilities',
        'workingCapitalRatio'
    );
    if (currentRatio !== null) {
        if (currentRatio > 2) scores.stability += 25;
        else if (currentRatio > 1.5) scores.stability += 20;
        else if (currentRatio > 1) scores.stability += 15;
        else if (currentRatio > 0.5) scores.stability += 10;
        else scores.stability += 5;
        
        if (currentRatio > 2) strengths.push('Liquidez excelente');
        else if (currentRatio < 1) weaknesses.push('Problemas de liquidez');
    }

    // Quick Ratio (Prueba Ácida)
    const quickRatio = getMetric('quickRatioTTM', 'quickRatio', 'acidTestRatio', 'liquidRatio');
    if (quickRatio !== null) {
        if (quickRatio > 1.5) scores.stability += 15;
        else if (quickRatio > 1) scores.stability += 12;
        else if (quickRatio > 0.5) scores.stability += 8;
        else scores.stability += 5;
    }

    // ========== 4. EFFICIENCY (Eficiencia) ==========
    // Margen Operativo
    const operatingMargin = getMetric(
        'operatingMarginTTM',
        'operatingMargin',
        'operatingProfitMargin',
        'ebitMargin',
        'operatingMarginAnnual'
    );
    if (operatingMargin !== null) {
        const margin = Math.abs(operatingMargin) > 1 ? Math.abs(operatingMargin) / 100 : Math.abs(operatingMargin);
        if (margin > 0.2) scores.efficiency += 30;
        else if (margin > 0.15) scores.efficiency += 25;
        else if (margin > 0.1) scores.efficiency += 20;
        else if (margin > 0.05) scores.efficiency += 15;
        else if (margin > 0) scores.efficiency += 10;
        
        if (margin > 0.2) strengths.push('Eficiencia operativa alta');
        else if (operatingMargin < 0) weaknesses.push('Margen operativo negativo');
    }

    // Rotación de Activos
    const assetTurnover = getMetric('assetTurnoverTTM', 'assetTurnover', 'totalAssetTurnover', 'assetsTurnover');
    if (assetTurnover !== null) {
        if (assetTurnover > 1) scores.efficiency += 20;
        else if (assetTurnover > 0.5) scores.efficiency += 15;
        else if (assetTurnover > 0.3) scores.efficiency += 10;
        else if (assetTurnover > 0.1) scores.efficiency += 5;
    }

    // ========== 5. VALUATION (Valuación) ==========
    // PER (Price to Earnings)
    const pe = getMetric('peTTM', 'pe', 'priceToEarnings', 'peRatio', 'priceEarningsRatio', 'priceEarnings');
    if (pe !== null && pe > 0) {
        if (pe < 15) scores.valuation += 25;
        else if (pe < 25) scores.valuation += 20;
        else if (pe < 35) scores.valuation += 15;
        else if (pe < 50) scores.valuation += 10;
        else scores.valuation += 5;
        
        if (pe < 15) strengths.push('Valuación atractiva (PER bajo)');
        else if (pe > 50) weaknesses.push('Sobrevaluación (PER alto)');
    }

    // P/B (Price to Book)
    const pb = getMetric('pbTTM', 'pb', 'priceToBook', 'priceBookRatio', 'priceBook');
    if (pb !== null && pb > 0) {
        if (pb < 2) scores.valuation += 20;
        else if (pb < 4) scores.valuation += 15;
        else if (pb < 8) scores.valuation += 10;
        else if (pb < 15) scores.valuation += 5;
        
        if (pb < 2) strengths.push('P/B razonable');
        else if (pb > 10) weaknesses.push('P/B muy alto');
    }

    // P/S (Price to Sales)
    const ps = getMetric('psTTM', 'ps', 'priceToSales', 'priceSalesRatio', 'priceSales');
    if (ps !== null && ps > 0) {
        if (ps < 2) scores.valuation += 15;
        else if (ps < 4) scores.valuation += 12;
        else if (ps < 8) scores.valuation += 8;
        else scores.valuation += 5;
    }

    // Normalizar scores individuales a 0-100
    const maxPossibleScores = {
        profitability: 75, // ROE (25) + ROA (25) + Net Margin (25)
        growth: 65, // Revenue Growth (25) + EBITDA Growth (25) + EPS Growth (15)
        stability: 70, // Debt to Equity (30) + Current Ratio (25) + Quick Ratio (15)
        efficiency: 50, // Operating Margin (30) + Asset Turnover (20)
        valuation: 60, // PE (25) + PB (20) + PS (15)
    };

    // Calcular porcentajes normalizados para cada categoría
    const profitabilityPercent = Math.min(100, Math.round((scores.profitability / maxPossibleScores.profitability) * 100));
    const growthPercent = Math.min(100, Math.round((scores.growth / maxPossibleScores.growth) * 100));
    const stabilityPercent = Math.min(100, Math.round((scores.stability / maxPossibleScores.stability) * 100));
    const efficiencyPercent = Math.min(100, Math.round((scores.efficiency / maxPossibleScores.efficiency) * 100));
    const valuationPercent = Math.min(100, Math.round((scores.valuation / maxPossibleScores.valuation) * 100));

    // Score total ponderado
    const totalScore = Math.min(100, Math.round(
        (profitabilityPercent * 0.25) +
        (growthPercent * 0.20) +
        (stabilityPercent * 0.25) +
        (efficiencyPercent * 0.15) +
        (valuationPercent * 0.15)
    ));

    // Calcular nota
    const grade = getGrade(totalScore);

    // Breakdown normalizado a 0-100
    const breakdown = {
        profitability: profitabilityPercent || 0,
        growth: growthPercent || 0,
        stability: stabilityPercent || 0,
        efficiency: efficiencyPercent || 0,
        valuation: valuationPercent || 0,
    };

    return {
        score: totalScore,
        grade,
        breakdown,
        strengths: strengths.slice(0, 5),
        weaknesses: weaknesses.slice(0, 5),
    };
}

export function getGrade(score: number): 'A+' | 'A' | 'A-' | 'B+' | 'B' | 'B-' | 'C+' | 'C' | 'C-' | 'D' | 'F' {
    if (score >= 95) return 'A+';
    if (score >= 90) return 'A';
    if (score >= 85) return 'A-';
    if (score >= 80) return 'B+';
    if (score >= 75) return 'B';
    if (score >= 70) return 'B-';
    if (score >= 65) return 'C+';
    if (score >= 60) return 'C';
    if (score >= 55) return 'C-';
    if (score >= 50) return 'D';
    return 'F';
}

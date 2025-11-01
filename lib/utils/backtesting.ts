/**
 * Sistema de Backtesting Básico
 * 
 * Permite evaluar estrategias ProPicks usando datos históricos
 */

export interface BacktestResult {
    strategyId: string;
    strategyName: string;
    period: {
        start: string;
        end: string;
        days: number;
    };
    performance: {
        totalReturn: number;        // Retorno total %
        annualizedReturn: number;   // Retorno anualizado %
        maxDrawdown: number;        // Drawdown máximo %
        sharpeRatio: number;        // Ratio de Sharpe
        winRate: number;            // Tasa de acierto %
        totalTrades: number;        // Total de operaciones
        avgHoldPeriod: number;      // Período promedio de tenencia (días)
    };
    picks: {
        symbol: string;
        entryPrice: number;
        exitPrice: number;
        return: number;
        holdPeriod: number;
        status: 'win' | 'loss';
    }[];
    vsBenchmark: {
        benchmarkReturn: number;    // Retorno del benchmark (S&P 500)
        alpha: number;              // Alpha (exceso de retorno vs benchmark)
        beta: number;               // Beta (sensibilidad al mercado)
    };
}

/**
 * Calcula métricas de backtesting básicas
 */
export function calculateBacktestMetrics(
    picks: Array<{
        symbol: string;
        entryPrice: number;
        exitPrice: number;
        entryDate: string;
        exitDate: string;
    }>,
    benchmarkReturns: number[], // Retornos diarios del benchmark
    startDate: string,
    endDate: string
): BacktestResult['performance'] {
    if (picks.length === 0) {
        return {
            totalReturn: 0,
            annualizedReturn: 0,
            maxDrawdown: 0,
            sharpeRatio: 0,
            winRate: 0,
            totalTrades: 0,
            avgHoldPeriod: 0,
        };
    }

    // Calcular retornos individuales
    const returns = picks.map(pick => {
        const return_ = ((pick.exitPrice - pick.entryPrice) / pick.entryPrice) * 100;
        const entry = new Date(pick.entryDate);
        const exit = new Date(pick.exitDate);
        const days = Math.max(1, Math.floor((exit.getTime() - entry.getTime()) / (1000 * 60 * 60 * 24)));
        return { return: return_, days, win: return_ > 0 };
    });

    // Retorno total (promedio igualmente ponderado)
    const totalReturn = returns.reduce((sum, r) => sum + r.return, 0) / returns.length;

    // Retorno anualizado
    const start = new Date(startDate);
    const end = new Date(endDate);
    const totalDays = Math.max(1, Math.floor((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)));
    const years = totalDays / 365.25;
    const annualizedReturn = years > 0 ? totalReturn / years : totalReturn;

    // Drawdown máximo (simplificado)
    const sortedReturns = [...returns].sort((a, b) => a.return - b.return);
    const maxDrawdown = sortedReturns.length > 0 ? Math.abs(Math.min(0, sortedReturns[0].return)) : 0;

    // Ratio de Sharpe (simplificado, asumiendo risk-free rate de 2%)
    const avgReturn = totalReturn;
    const returnStdDev = calculateStandardDeviation(returns.map(r => r.return));
    const riskFreeRate = 2; // 2% anual
    const sharpeRatio = returnStdDev > 0 ? (avgReturn - riskFreeRate) / returnStdDev : 0;

    // Tasa de acierto
    const wins = returns.filter(r => r.win).length;
    const winRate = (wins / returns.length) * 100;

    // Período promedio de tenencia
    const avgHoldPeriod = returns.reduce((sum, r) => sum + r.days, 0) / returns.length;

    return {
        totalReturn,
        annualizedReturn,
        maxDrawdown,
        sharpeRatio,
        winRate,
        totalTrades: picks.length,
        avgHoldPeriod: Math.round(avgHoldPeriod),
    };
}

/**
 * Calcula desviación estándar
 */
function calculateStandardDeviation(values: number[]): number {
    if (values.length === 0) return 0;
    
    const mean = values.reduce((sum, val) => sum + val, 0) / values.length;
    const squaredDiffs = values.map(val => Math.pow(val - mean, 2));
    const variance = squaredDiffs.reduce((sum, val) => sum + val, 0) / values.length;
    
    return Math.sqrt(variance);
}

/**
 * Simula una estrategia de ProPicks con datos históricos
 * 
 * @param strategyId ID de la estrategia
 * @param picks Selección de picks (símbolos con fechas)
 * @param historicalPrices Precios históricos por símbolo
 * @param benchmarkPrices Precios históricos del benchmark (S&P 500)
 */
export function simulateStrategy(
    strategyId: string,
    strategyName: string,
    picks: Array<{
        symbol: string;
        entryDate: string;
        entryPrice: number;
    }>,
    historicalPrices: Record<string, Array<{ date: string; price: number }>>,
    benchmarkPrices: Array<{ date: string; price: number }>,
    holdPeriodDays: number = 30 // Período de tenencia por defecto (30 días)
): BacktestResult {
    const startDate = picks.length > 0 ? picks[0].entryDate : new Date().toISOString();
    const endDate = new Date(startDate);
    endDate.setDate(endDate.getDate() + holdPeriodDays);
    const endDateStr = endDate.toISOString();

    // Simular salida de cada pick
    const pickResults = picks.map(pick => {
        const prices = historicalPrices[pick.symbol] || [];
        const entryDate = new Date(pick.entryDate);
        const exitDate = new Date(entryDate);
        exitDate.setDate(exitDate.getDate() + holdPeriodDays);

        // Buscar precio de salida más cercano
        let exitPrice = pick.entryPrice; // Por defecto, mismo precio
        for (const priceData of prices) {
            const priceDate = new Date(priceData.date);
            if (priceDate >= exitDate || Math.abs(priceDate.getTime() - exitDate.getTime()) < 86400000) {
                exitPrice = priceData.price;
                break;
            }
        }

        const return_ = ((exitPrice - pick.entryPrice) / pick.entryPrice) * 100;
        const holdPeriod = Math.floor((exitDate.getTime() - entryDate.getTime()) / (1000 * 60 * 60 * 24));

        return {
            symbol: pick.symbol,
            entryPrice: pick.entryPrice,
            exitPrice,
            return: return_,
            holdPeriod: Math.max(1, holdPeriod),
            status: return_ > 0 ? 'win' as const : 'loss' as const,
        };
    });

    // Calcular retorno del benchmark en el mismo período
    const startBenchmark = benchmarkPrices.find(p => new Date(p.date) >= new Date(startDate));
    const endBenchmark = benchmarkPrices.find(p => new Date(p.date) >= new Date(endDateStr));
    
    let benchmarkReturn = 0;
    if (startBenchmark && endBenchmark) {
        benchmarkReturn = ((endBenchmark.price - startBenchmark.price) / startBenchmark.price) * 100;
    }

    const performance = calculateBacktestMetrics(
        pickResults.map(p => ({
            symbol: p.symbol,
            entryPrice: p.entryPrice,
            exitPrice: p.exitPrice,
            entryDate: startDate,
            exitDate: endDateStr,
        })),
        [], // benchmarkReturns simplificado
        startDate,
        endDateStr
    );

    // Calcular Alpha y Beta (simplificado)
    const alpha = performance.totalReturn - benchmarkReturn;
    const beta = 1.0; // Por defecto, asumimos beta de 1.0

    return {
        strategyId,
        strategyName,
        period: {
            start: startDate,
            end: endDateStr,
            days: holdPeriodDays,
        },
        performance,
        picks: pickResults,
        vsBenchmark: {
            benchmarkReturn,
            alpha,
            beta,
        },
    };
}

/**
 * Formatea resultado de backtesting para visualización
 */
export function formatBacktestResult(result: BacktestResult): {
    summary: string;
    details: Array<{ label: string; value: string; color: string }>;
} {
    const details = [
        {
            label: 'Retorno Total',
            value: `${result.performance.totalReturn > 0 ? '+' : ''}${result.performance.totalReturn.toFixed(2)}%`,
            color: result.performance.totalReturn > 0 ? 'text-green-400' : 'text-red-400',
        },
        {
            label: 'Retorno Anualizado',
            value: `${result.performance.annualizedReturn > 0 ? '+' : ''}${result.performance.annualizedReturn.toFixed(2)}%`,
            color: result.performance.annualizedReturn > 0 ? 'text-green-400' : 'text-red-400',
        },
        {
            label: 'vs S&P 500',
            value: `${result.vsBenchmark.alpha > 0 ? '+' : ''}${result.vsBenchmark.alpha.toFixed(2)}%`,
            color: result.vsBenchmark.alpha > 0 ? 'text-green-400' : 'text-red-400',
        },
        {
            label: 'Tasa de Acierto',
            value: `${result.performance.winRate.toFixed(1)}%`,
            color: result.performance.winRate > 50 ? 'text-green-400' : 'text-yellow-400',
        },
        {
            label: 'Sharpe Ratio',
            value: result.performance.sharpeRatio.toFixed(2),
            color: result.performance.sharpeRatio > 1 ? 'text-green-400' : result.performance.sharpeRatio > 0 ? 'text-yellow-400' : 'text-red-400',
        },
        {
            label: 'Max Drawdown',
            value: `${result.performance.maxDrawdown.toFixed(2)}%`,
            color: result.performance.maxDrawdown < 10 ? 'text-green-400' : result.performance.maxDrawdown < 20 ? 'text-yellow-400' : 'text-red-400',
        },
    ];

    const summary = `${result.strategyName}: ${result.performance.totalReturn > 0 ? '+' : ''}${result.performance.totalReturn.toFixed(2)}% en ${result.period.days} días (vs S&P 500: ${result.vsBenchmark.alpha > 0 ? '+' : ''}${result.vsBenchmark.alpha.toFixed(2)}%)`;

    return { summary, details };
}


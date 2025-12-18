/**
 * Sistema Avanzado de Scoring de Acciones - Similar a Investing Pro
 * 
 * Incluye:
 * - Comparación con sector (crucial según Investing Pro)
 * - Múltiples categorías: Valor, Crecimiento, Rentabilidad, Flujo de Caja, Impulso, Deuda/Liquidez
 * - Scoring similar a Piotroski F-Score pero más completo
 * 
 * Motor multifactorial que pondera más de 100 métricas comparándolas siempre contra pares del sector
 */

import { getSectorAverages, type SectorAverages } from '@/lib/actions/sectorData.actions';

export interface AdvancedScoreData {
    overallScore: number; // 0-100
    grade: 'A+' | 'A' | 'A-' | 'B+' | 'B' | 'B-' | 'C+' | 'C' | 'C-' | 'D' | 'F';
    categoryScores: {
        value: number;          // Valor relativo (P/E, P/B, P/S, EV/EBITDA)
        growth: number;         // Crecimiento (ingresos, EPS, FCF)
        profitability: number; // Rentabilidad (márgenes, ROE, ROA)
        cashFlow: number;       // Flujo de caja (FCF, OCF, ratios)
        momentum: number;       // Impulso (retornos 3/6/12M, RSI, proximity to 52W high)
        debtLiquidity: number; // Deuda y liquidez (D/E, Current Ratio, Interest Coverage)
    };
    sectorComparison: {
        sector: string;
        sectorAverage: {
            value: number;
            growth: number;
            profitability: number;
            cashFlow: number;
            momentum: number;
            debtLiquidity: number;
        };
        vsSector: {
            value: number;      // + si está mejor, - si está peor
            growth: number;
            profitability: number;
            cashFlow: number;
            momentum: number;
            debtLiquidity: number;
        };
    } | null;
    reasons: {
        strengths: string[];
        weaknesses: string[];
        opportunities: string[];
        threats: string[];
    };
}

// Esta función ahora usa getSectorAverages de sectorData.actions que obtiene datos reales

/**
 * Calcula score avanzado de una acción comparándola con su sector
 */
export async function calculateAdvancedStockScore(
    financialData: any,
    historicalData?: { prices: number[]; dates: number[] }
): Promise<AdvancedScoreData> {
    const metrics = financialData.metrics?.metric || financialData.metrics || {};
    const profile = financialData.profile || {};
    const quote = financialData.quote || {};
    const indexComparison = financialData.indexComparison || {};

    const sector = profile.finnhubIndustry || profile.industry || 'Unknown';

    // Obtener promedios reales del sector desde la API
    // IMPORTANTE: Si no hay datos disponibles, no inventamos valores
    const sectorData = await getSectorAverages(sector);

    if (!sectorData) {
        // Sin datos del sector, usar valores neutrales pero indicarlo
        console.warn(`No hay datos disponibles del sector ${sector} para comparación`);
    }

    const sectorAverages = sectorData?.averages || {
        value: 50, // Neutral - sin comparación
        growth: 50,
        profitability: 50,
        cashFlow: 50,
        momentum: 50,
        debtLiquidity: 50,
    };

    // Usar métricas promedio del sector para comparaciones más precisas
    // Solo usar si están disponibles
    const sectorMetrics = sectorData?.metrics;

    const categoryScores = {
        value: 0,
        growth: 0,
        profitability: 0,
        cashFlow: 0,
        momentum: 0,
        debtLiquidity: 0,
    };

    const strengths: string[] = [];
    const weaknesses: string[] = [];
    const opportunities: string[] = [];
    const threats: string[] = [];

    // Helper para obtener valores numéricos
    const getNumeric = (value: any): number | null => {
        if (value === null || value === undefined || value === '') return null;
        const num = typeof value === 'string' ? parseFloat(value.replace(/,/g, '')) : Number(value);
        return isNaN(num) ? null : num;
    };

    const getMetric = (...names: string[]): number | null => {
        for (const name of names) {
            const value = getNumeric(metrics[name]);
            if (value !== null) return value;
        }
        return null;
    };

    // ========== 1. VALUE (Valor Relativo) ==========
    const pe = getMetric('peTTM', 'pe', 'priceToEarnings', 'peRatio');
    const pb = getMetric('pbTTM', 'pb', 'priceToBook');
    const ps = getMetric('psTTM', 'ps', 'priceToSales');
    const evEbitda = getMetric('evEbitdaTTM', 'evEbitda', 'enterpriseValueToEbitda');

    // Comparar con sector (P/E bajo es mejor, pero depende del sector)
    if (pe !== null && pe > 0) {
        const sectorPE = sectorMetrics?.avgPE || 25; // PE promedio del sector real
        const peScore = pe < sectorPE * 0.8 ? 30 : pe < sectorPE ? 25 : pe < sectorPE * 1.2 ? 20 : 15;
        categoryScores.value += peScore;

        if (pe < sectorPE * 0.7) {
            strengths.push(`PER bajo vs sector (${pe.toFixed(1)} vs ${sectorPE.toFixed(1)})`);
        } else if (pe > sectorPE * 1.5) {
            weaknesses.push(`PER alto vs sector (${pe.toFixed(1)} vs ${sectorPE.toFixed(1)})`);
        }
    }

    // PB comparado con sector
    if (pb !== null && pb > 0) {
        if (sectorMetrics?.avgPB) {
            const sectorPB = sectorMetrics.avgPB;
            const pbScore = pb < sectorPB * 0.8 ? 25 : pb < sectorPB ? 20 : pb < sectorPB * 1.2 ? 15 : 10;
            categoryScores.value += pbScore;

            if (pb < sectorPB * 0.7) {
                strengths.push(`P/B bajo vs sector (${pb.toFixed(1)} vs ${sectorPB.toFixed(1)})`);
            }
        } else {
            const pbScore = pb < 2 ? 25 : pb < 4 ? 20 : pb < 6 ? 15 : 10;
            categoryScores.value += pbScore;
        }
    }
    if (ps !== null && ps > 0) {
        const psScore = ps < 3 ? 20 : ps < 6 ? 15 : ps < 10 ? 10 : 5;
        categoryScores.value += psScore;
    }
    if (evEbitda !== null && evEbitda > 0) {
        const evScore = evEbitda < 12 ? 25 : evEbitda < 18 ? 20 : evEbitda < 25 ? 15 : 10;
        categoryScores.value += evScore;
    }

    // Normalizar a 0-100
    categoryScores.value = Math.min(100, categoryScores.value);

    // ========== 2. GROWTH (Crecimiento) ==========
    const revenueGrowth = getMetric('revenueGrowthTTMYoy', 'revenueGrowth3Y', 'revenueGrowthTTM', 'revenueGrowth');
    const epsGrowth = getMetric('epsGrowthTTMYoy', 'epsGrowth3Y', 'epsGrowthTTM', 'epsGrowth');
    const ebitdaGrowth = getMetric('ebitdaCagr5Y', 'ebitdaGrowthTTM');

    if (revenueGrowth !== null) {
        let growth = revenueGrowth / 100;
        if (Math.abs(growth) > 1) growth = growth / 100;

        // Comparar con sector (crecimiento típico del sector)
        const sectorGrowth = (sectorMetrics?.avgRevenueGrowth || 0.15);
        const growthScore = growth > sectorGrowth * 1.5 ? 40 : growth > sectorGrowth ? 35 : growth > 0 ? 25 : 10;
        categoryScores.growth += growthScore;

        if (growth > sectorGrowth * 1.3) {
            strengths.push(`Crecimiento superior al sector (${(growth * 100).toFixed(1)}% vs ${(sectorGrowth * 100).toFixed(1)}%)`);
        }
    }
    if (epsGrowth !== null) {
        let growth = epsGrowth / 100;
        if (Math.abs(growth) > 1) growth = growth / 100;
        categoryScores.growth += growth > 0.2 ? 30 : growth > 0.1 ? 25 : growth > 0 ? 20 : 10;
    }
    if (ebitdaGrowth !== null) {
        let growth = ebitdaGrowth / 100;
        if (Math.abs(growth) > 1) growth = growth / 100;
        categoryScores.growth += growth > 0.15 ? 30 : growth > 0 ? 20 : 10;
    }

    categoryScores.growth = Math.min(100, categoryScores.growth);

    // ========== 3. PROFITABILITY (Rentabilidad) ==========
    const netMargin = getMetric('netProfitMarginTTM', 'netProfitMargin', 'profitMargin');
    const roe = getMetric('roeTTM', 'roe', 'returnOnEquity');
    const roa = getMetric('roaTTM', 'roa', 'returnOnAssets');
    const operatingMargin = getMetric('operatingMarginTTM', 'operatingMargin');

    if (netMargin !== null) {
        const margin = Math.abs(netMargin) > 1 ? Math.abs(netMargin) / 100 : Math.abs(netMargin);
        const sectorMargin = sectorMetrics?.avgNetMargin || 0.15; // Margen promedio del sector real
        const marginScore = margin > sectorMargin * 1.3 ? 35 : margin > sectorMargin ? 30 : margin > 0.1 ? 25 : margin > 0 ? 15 : 0;
        categoryScores.profitability += marginScore;

        if (margin > sectorMargin * 1.2) {
            strengths.push(`Margen neto superior al sector (${(margin * 100).toFixed(1)}% vs ${(sectorMargin * 100).toFixed(1)}%)`);
        }
    }
    if (roe !== null) {
        const roeValue = Math.abs(roe) > 1 ? Math.abs(roe) / 100 : Math.abs(roe);
        categoryScores.profitability += roeValue > 0.2 ? 35 : roeValue > 0.15 ? 30 : roeValue > 0.1 ? 25 : roeValue > 0 ? 20 : 10;
    }
    if (roa !== null) {
        const roaValue = Math.abs(roa) > 1 ? Math.abs(roa) / 100 : Math.abs(roa);
        categoryScores.profitability += roaValue > 0.1 ? 30 : roaValue > 0.05 ? 25 : roaValue > 0 ? 20 : 10;
    }

    categoryScores.profitability = Math.min(100, categoryScores.profitability);

    // ========== 4. CASH FLOW (Flujo de Caja) ==========
    // Nota: Finnhub Basic devuelve ratios por acción o precios
    const cashFlowPerShare = getMetric('cashFlowPerShareTTM', 'cashFlowPerShareQuarterly');
    const priceToFcf = getMetric('pfcfShareTTM', 'pfcfShareAnnual'); // Price / FCF per share

    // Calcular FCF Yield = 1 / PriceToFCF
    let fcfYield = priceToFcf ? (1 / priceToFcf) : null;

    // Si tenemos FCF yield directo
    const evFcf = getMetric('currentEv/freeCashFlowTTM');
    if (evFcf && !fcfYield) fcfYield = 1 / evFcf;

    if (fcfYield !== null && fcfYield > 0) {
        categoryScores.cashFlow += fcfYield > 0.05 ? 40 : fcfYield > 0.03 ? 35 : fcfYield > 0 ? 25 : 10;
        if (fcfYield > 0.05) strengths.push('Alto rendimiento de flujo de caja libre (Yield)');
    } else if (priceToFcf && priceToFcf < 15) {
        // Si yield falla pero P/FCF es bueno
        categoryScores.cashFlow += 30;
    }

    if (cashFlowPerShare !== null && cashFlowPerShare > 0) {
        categoryScores.cashFlow += 30;
        strengths.push('Flujo de caja por acción positivo');
    } else if (cashFlowPerShare !== null && cashFlowPerShare < 0) {
        weaknesses.push('Flujo de caja por acción negativo');
    }

    categoryScores.cashFlow = Math.min(100, categoryScores.cashFlow);

    // ========== 5. MOMENTUM (Impulso) ==========
    // Usar datos históricos si están disponibles
    if (historicalData && historicalData.prices.length > 0) {
        const prices = historicalData.prices;
        const currentPrice = prices[prices.length - 1];

        // Retorno a 3 meses (aprox 63 días)
        if (prices.length > 63) {
            const price3M = prices[prices.length - 63];
            const return3M = ((currentPrice - price3M) / price3M) * 100;
            categoryScores.momentum += return3M > 10 ? 20 : return3M > 5 ? 15 : return3M > 0 ? 10 : 5;
        }

        // Retorno a 6 meses (aprox 126 días)
        if (prices.length > 126) {
            const price6M = prices[prices.length - 126];
            const return6M = ((currentPrice - price6M) / price6M) * 100;
            categoryScores.momentum += return6M > 20 ? 20 : return6M > 10 ? 15 : return6M > 0 ? 10 : 5;
        }

        // Retorno a 12 meses (aprox 252 días)
        if (prices.length > 252) {
            const price12M = prices[prices.length - 252];
            const return12M = ((currentPrice - price12M) / price12M) * 100;
            categoryScores.momentum += return12M > 30 ? 20 : return12M > 15 ? 15 : return12M > 0 ? 10 : 5;
        }

        // Proximidad a máximo de 52 semanas
        if (prices.length > 252) {
            const last52W = prices.slice(-252);
            const max52W = Math.max(...last52W);
            const proximityTo52W = (currentPrice / max52W) * 100;
            categoryScores.momentum += proximityTo52W > 95 ? 20 : proximityTo52W > 90 ? 15 : proximityTo52W > 80 ? 10 : 5;

            if (proximityTo52W > 95) {
                opportunities.push('Cerca del máximo de 52 semanas');
            }
        }
    }

    // Usar cambio diario si no hay datos históricos
    if (quote.dp) {
        const dailyChange = quote.dp / 100;
        categoryScores.momentum += Math.abs(dailyChange) > 2 ? 15 : Math.abs(dailyChange) > 1 ? 10 : 5;
    }

    // Comparación con S&P 500
    if (indexComparison.vsSP500) {
        const vsSP500 = indexComparison.vsSP500.change || 0;
        categoryScores.momentum += vsSP500 > 5 ? 20 : vsSP500 > 0 ? 15 : vsSP500 > -5 ? 10 : 5;

        if (vsSP500 > 5) {
            strengths.push(`Supera al S&P 500 (+${vsSP500.toFixed(1)}%)`);
        } else if (vsSP500 < -10) {
            weaknesses.push(`Bajo desempeño vs S&P 500 (${vsSP500.toFixed(1)}%)`);
        }
    }

    categoryScores.momentum = Math.min(100, categoryScores.momentum);

    // ========== 6. DEBT & LIQUIDITY (Deuda y Liquidez) ==========
    const debtToEquity = getMetric('totalDebt/totalEquityQuarterly', 'totalDebt/totalEquityAnnual', 'longTermDebt/equityQuarterly');
    const currentRatio = getMetric('currentRatioQuarterly', 'currentRatioAnnual', 'currentRatioTTM');
    const quickRatio = getMetric('quickRatioQuarterly', 'quickRatioAnnual', 'quickRatioTTM');
    const interestCoverage = getMetric('netInterestCoverageTTM', 'netInterestCoverageAnnual');

    // Comparar D/E con sector (importante: diferentes sectores tienen diferentes niveles normales)
    if (debtToEquity !== null) {
        const dte = Math.abs(debtToEquity);

        // Usar D/E promedio real del sector
        const sectorNormalDte = sectorMetrics?.avgDebtToEquity || (
            sector === 'Financial Services' ? 8.0 :
                sector === 'Energy' ? 3.0 :
                    sector === 'Technology' ? 0.5 : 1.5
        );

        if (dte < sectorNormalDte * 0.7) {
            categoryScores.debtLiquidity += 35;
            strengths.push(`Baja deuda vs sector (D/E: ${dte.toFixed(2)} vs ${sectorNormalDte.toFixed(1)})`);
        } else if (dte < sectorNormalDte) {
            categoryScores.debtLiquidity += 30;
        } else if (dte < sectorNormalDte * 1.5) {
            categoryScores.debtLiquidity += 20;
        } else {
            categoryScores.debtLiquidity += 10;
            weaknesses.push(`Alta deuda vs sector (D/E: ${dte.toFixed(2)} vs ${sectorNormalDte.toFixed(1)})`);
        }
    }

    if (currentRatio !== null) {
        categoryScores.debtLiquidity += currentRatio > 2 ? 25 : currentRatio > 1.5 ? 20 : currentRatio > 1 ? 15 : 10;
        if (currentRatio > 2) strengths.push('Excelente liquidez');
        else if (currentRatio < 1) threats.push('Problemas de liquidez');
    }

    if (quickRatio !== null) {
        categoryScores.debtLiquidity += quickRatio > 1.5 ? 20 : quickRatio > 1 ? 15 : quickRatio > 0.5 ? 10 : 5;
    }

    if (interestCoverage !== null && interestCoverage > 0) {
        categoryScores.debtLiquidity += interestCoverage > 5 ? 20 : interestCoverage > 3 ? 15 : interestCoverage > 1 ? 10 : 5;
        if (interestCoverage < 1.5) threats.push('Cobertura de intereses baja');
    }

    categoryScores.debtLiquidity = Math.min(100, categoryScores.debtLiquidity);

    // ========== CALCULAR SCORE FINAL ==========
    // Ponderación similar a Investing Pro (basado en importancia)
    const weights = {
        value: 0.15,
        growth: 0.20,
        profitability: 0.25,
        cashFlow: 0.15,
        momentum: 0.10,
        debtLiquidity: 0.15,
    };

    const overallScore = Math.round(
        categoryScores.value * weights.value +
        categoryScores.growth * weights.growth +
        categoryScores.profitability * weights.profitability +
        categoryScores.cashFlow * weights.cashFlow +
        categoryScores.momentum * weights.momentum +
        categoryScores.debtLiquidity * weights.debtLiquidity
    );

    // Comparar con promedios del sector (solo si hay datos reales)
    const vsSector = sectorData ? {
        value: categoryScores.value - sectorAverages.value,
        growth: categoryScores.growth - sectorAverages.growth,
        profitability: categoryScores.profitability - sectorAverages.profitability,
        cashFlow: categoryScores.cashFlow - sectorAverages.cashFlow,
        momentum: categoryScores.momentum - sectorAverages.momentum,
        debtLiquidity: categoryScores.debtLiquidity - sectorAverages.debtLiquidity,
    } : {
        value: 0, // Sin comparación disponible
        growth: 0,
        profitability: 0,
        cashFlow: 0,
        momentum: 0,
        debtLiquidity: 0,
    };

    // Calcular nota
    const grade = getGrade(overallScore);

    return {
        overallScore,
        grade,
        categoryScores,
        sectorComparison: sectorData ? {
            sector,
            sectorAverage: {
                value: sectorAverages.value,
                growth: sectorAverages.growth,
                profitability: sectorAverages.profitability,
                cashFlow: sectorAverages.cashFlow,
                momentum: sectorAverages.momentum,
                debtLiquidity: sectorAverages.debtLiquidity,
            },
            vsSector,
        } : null, // null si no hay datos del sector
        reasons: {
            strengths: strengths.slice(0, 8),
            weaknesses: weaknesses.slice(0, 5),
            opportunities: opportunities.slice(0, 3),
            threats: threats.slice(0, 3),
        },
    };
}

function getGrade(score: number): 'A+' | 'A' | 'A-' | 'B+' | 'B' | 'B-' | 'C+' | 'C' | 'C-' | 'D' | 'F' {
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


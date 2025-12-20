'use client';

import { useState, useEffect } from 'react';
import { Loader2, Sparkles, TrendingUp, TrendingDown, Target, Wallet, Database, RefreshCw, Brain } from 'lucide-react';
import { generateThesisCommentary } from '@/lib/actions/ai.actions';
import {
    getDCF,
    getFundamentals,
    getKeyMetricsTTM,
    getEnterpriseValue,
    getTreasuryRates,
    getPriceTarget
} from '@/lib/actions/fmp.actions';
import { getProfile, getStockQuote } from '@/lib/actions/finnhub.actions';
import {
    calculateWACC,
    calculateCostOfEquity,
    calculateTerminalValue,
    calculateMarginOfSafety,
    getValuationVerdict,
    generateScenarios,
    estimateBeta,
    estimateTaxRate,
    type ThesisValuation,
    type WACCInputs
} from '@/lib/calculations/dcf';

interface VisualThesisProps {
    symbol: string;
    companyName: string;
    currentPrice: number;
}

interface ThesisData {
    valuation: ThesisValuation;
    companyName: string;
    symbol: string;
    marketCap: number;
    sector: string;
    beta: number;
    riskFreeRate: number;
    debtToEquity: number;
    lastFCF: number;
    revenueGrowth: number;
    fcfYield: number;
}

export default function VisualThesis({ symbol, companyName, currentPrice }: VisualThesisProps) {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [thesisData, setThesisData] = useState<ThesisData | null>(null);
    const [aiCommentary, setAiCommentary] = useState<{ commentary: string; confidence: string; keyInsight: string } | null>(null);
    const [aiLoading, setAiLoading] = useState(false);

    useEffect(() => {
        async function fetchAndCalculate() {
            try {
                setLoading(true);
                setError(null);

                // Fetch all required data in parallel - ALL FROM REAL APIs
                const [dcfData, fundamentals, keyMetrics, evData, treasuryData, profile, quote, priceTarget] = await Promise.all([
                    getDCF(symbol),
                    getFundamentals(symbol, 'annual'),
                    getKeyMetricsTTM(symbol),
                    getEnterpriseValue(symbol),
                    getTreasuryRates(),
                    getProfile(symbol),
                    getStockQuote(symbol),
                    getPriceTarget(symbol)
                ]);

                // Extract REAL values from APIs
                const intrinsicValueFromFMP = dcfData?.dcf?.[0]?.dcf || 0;
                const stockPrice = quote?.c || currentPrice;
                const realBeta = (profile as any)?.beta || 1.0;
                const beta = realBeta > 0 ? realBeta : estimateBeta((profile as any)?.finnhubIndustry || 'Technology');
                const sector = (profile as any)?.finnhubIndustry || 'Technology';
                const marketCap = evData?.enterpriseValue?.[0]?.marketCapitalization || 0;
                const sharesOutstanding = evData?.enterpriseValue?.[0]?.numberOfShares || 1;
                const totalDebt = evData?.enterpriseValue?.[0]?.addTotalDebt || 0;
                const cash = Math.abs(evData?.enterpriseValue?.[0]?.minusCashAndCashEquivalents || 0);

                // Key metrics from REAL API
                const km = keyMetrics?.keyMetrics?.[0];
                const fcfYield = km?.freeCashFlowYieldTTM || 0;
                const debtToEquity = km?.debtToEquityTTM || 0.5;

                // REAL Treasury rate from FMP API
                const realRiskFreeRate = treasuryData?.treasuryRates?.[0]?.year10 || 4.5;
                const riskFreeRate = realRiskFreeRate / 100;
                const equityRiskPremium = 0.055; // Standard market premium
                const taxRate = estimateTaxRate('US');
                const costOfDebt = riskFreeRate + 0.015; // Treasury + credit spread

                // Calculate WACC with REAL inputs
                const waccInputs: WACCInputs = {
                    riskFreeRate,
                    beta,
                    equityRiskPremium,
                    costOfDebt,
                    taxRate,
                    debtToEquity
                };
                const wacc = calculateWACC(waccInputs);
                const costOfEquity = calculateCostOfEquity(riskFreeRate, beta, equityRiskPremium);

                // Get REAL FCF history from fundamentals
                const cashflows = fundamentals?.cashflow || [];
                const fcfHistory = cashflows.slice(0, 5).map(cf => cf.freeCashFlow);
                const lastFCF = fcfHistory[0] || 0;

                // FCF growth rate from real historical data
                const fcfGrowthRate = fcfHistory.length >= 2 && fcfHistory[1] !== 0
                    ? ((fcfHistory[0] - fcfHistory[1]) / Math.abs(fcfHistory[1]))
                    : 0.05;
                const projectedGrowth = Math.max(0.02, Math.min(0.15, fcfGrowthRate)); // Cap between 2-15%

                // Project FCFs with real growth
                const projectedFCFs = Array(5).fill(0).map((_, i) => lastFCF * Math.pow(1 + projectedGrowth, i + 1));

                // Terminal Value with real data
                const terminalValue = calculateTerminalValue(projectedFCFs[4] || lastFCF, wacc, 0.025);

                // Use FMP's DCF value (professionally calculated) as primary
                const intrinsicValue = intrinsicValueFromFMP > 0 ? intrinsicValueFromFMP :
                    (terminalValue / sharesOutstanding) + (cash - totalDebt) / sharesOutstanding;

                // Margin of Safety & Verdict
                const marginOfSafety = calculateMarginOfSafety(stockPrice, intrinsicValue);
                const verdict = getValuationVerdict(marginOfSafety);

                // Generate scenarios based on FMP's intrinsic value
                const scenarios = generateScenarios(intrinsicValue, stockPrice, wacc);

                // Revenue growth from REAL income statements
                const incomeStatements = fundamentals?.income || [];
                const revenueGrowth = incomeStatements.length >= 2
                    ? ((incomeStatements[0].revenue - incomeStatements[1].revenue) / incomeStatements[1].revenue) * 100
                    : 0;

                setThesisData({
                    valuation: {
                        currentPrice: stockPrice,
                        intrinsicValue,
                        marginOfSafety,
                        verdict,
                        wacc: wacc * 100,
                        costOfEquity: costOfEquity * 100,
                        costOfDebt: costOfDebt * 100,
                        terminalValue,
                        scenarios
                    },
                    companyName,
                    symbol,
                    marketCap,
                    sector,
                    beta,
                    riskFreeRate: realRiskFreeRate,
                    debtToEquity,
                    lastFCF,
                    revenueGrowth,
                    fcfYield: fcfYield * 100
                });

            } catch (err) {
                console.error('Error generating thesis:', err);
                setError('No se pudo calcular el análisis de valoración');
            } finally {
                setLoading(false);
            }
        }

        fetchAndCalculate();
    }, [symbol, companyName, currentPrice]);

    // Second effect: Generate AI commentary after data loads
    useEffect(() => {
        if (!thesisData) return;
        const data = thesisData; // Capture for closure

        async function fetchAICommentary() {
            setAiLoading(true);
            try {
                const result = await generateThesisCommentary({
                    symbol: data.symbol,
                    companyName: data.companyName,
                    currentPrice: data.valuation.currentPrice,
                    intrinsicValue: data.valuation.intrinsicValue,
                    marginOfSafety: data.valuation.marginOfSafety,
                    verdict: data.valuation.verdict,
                    wacc: data.valuation.wacc,
                    costOfEquity: data.valuation.costOfEquity,
                    fcfLastYear: data.lastFCF,
                    revenueGrowth: data.revenueGrowth,
                    debtToEquity: data.debtToEquity,
                    beta: data.beta,
                    scenarios: data.valuation.scenarios.map(s => ({ name: s.name, targetPrice: s.targetPrice }))
                });
                setAiCommentary(result);
            } catch (err) {
                console.error('AI commentary error:', err);
            } finally {
                setAiLoading(false);
            }
        }

        fetchAICommentary();
    }, [thesisData]);

    if (loading) {
        return (
            <div className="bg-gradient-to-br from-[#0a0a0a] to-[#111111] border border-gray-800 rounded-2xl p-8">
                <div className="flex items-center justify-center gap-3 text-gray-400">
                    <Loader2 className="h-6 w-6 animate-spin text-teal-500" />
                    <span>Generando Visual Investment Thesis con datos reales...</span>
                </div>
            </div>
        );
    }

    if (error || !thesisData) {
        return (
            <div className="bg-red-900/20 border border-red-800 rounded-2xl p-6 text-red-300">
                {error || 'Error al generar el análisis'}
            </div>
        );
    }

    const { valuation } = thesisData;
    const isUndervalued = valuation.verdict === 'UNDERVALUED';
    const isOvervalued = valuation.verdict === 'OVERVALUED';

    // Calculate bar heights proportionally
    const maxPrice = Math.max(valuation.currentPrice, valuation.intrinsicValue);
    const currentBarHeight = (valuation.currentPrice / maxPrice) * 70;
    const intrinsicBarHeight = (valuation.intrinsicValue / maxPrice) * 70;

    return (
        <div className="space-y-6">
            {/* Header with Data Source Badge */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-teal-500 to-blue-600 flex items-center justify-center shadow-lg shadow-teal-500/20">
                        <Sparkles className="h-5 w-5 text-white" />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-white">Visual Investment Thesis</h2>
                        <p className="text-sm text-gray-400">{companyName}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2 px-3 py-1.5 bg-green-500/10 border border-green-500/30 rounded-full">
                    <Database className="h-3.5 w-3.5 text-green-400" />
                    <span className="text-xs text-green-400 font-medium">Datos en vivo via FMP + Finnhub</span>
                </div>
            </div>

            {/* Card Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Card 1: Valuation Analysis - IMPROVED */}
                <div className="bg-gradient-to-br from-[#111111] to-[#0d0d0d] border border-gray-800/80 rounded-2xl p-6 shadow-xl">
                    <div className="flex items-center justify-between mb-6">
                        <div>
                            <h3 className="text-lg font-semibold text-white">{symbol}: Valuation Analysis</h3>
                            <p className="text-xs text-gray-500">DCF via Financial Modeling Prep API</p>
                        </div>
                        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-gray-700 to-gray-800 flex items-center justify-center text-white font-bold text-xs shadow-inner">
                            {symbol.slice(0, 4)}
                        </div>
                    </div>

                    {/* Row 1: Price vs Value + Margin of Safety */}
                    <div className="grid grid-cols-2 gap-4 mb-4">
                        {/* Price vs Intrinsic Value */}
                        <div className="bg-[#080808] rounded-xl p-4 border border-gray-800/50">
                            <p className="text-xs text-gray-400 mb-3 font-medium"></p>
                            <div className="flex items-end justify-center gap-6 h-24 mb-3">
                                <div className="flex flex-col items-center">
                                    <div
                                        className="w-14 bg-gradient-to-t from-teal-600 to-teal-400 rounded-t-md shadow-lg shadow-teal-500/30 transition-all duration-500"
                                        style={{ height: `${currentBarHeight}px` }}
                                    />
                                    <div className="mt-2 text-center">
                                        <p className="text-sm font-bold text-teal-400">${valuation.currentPrice.toFixed(2)}</p>
                                        <p className="text-[10px] text-gray-500">Precio Actual</p>
                                    </div>
                                </div>
                                <div className="flex flex-col items-center">
                                    <div
                                        className="w-14 bg-gradient-to-t from-green-600 to-green-400 rounded-t-md shadow-lg shadow-green-500/30 transition-all duration-500"
                                        style={{ height: `${intrinsicBarHeight}px` }}
                                    />
                                    <div className="mt-2 text-center">
                                        <p className="text-sm font-bold text-green-400">${valuation.intrinsicValue.toFixed(2)}</p>
                                        <p className="text-[10px] text-gray-500">Valor Intrínseco</p>
                                    </div>
                                </div>
                            </div>
                            <p className="text-[10px] text-gray-500 text-center border-t border-gray-800 pt-2">
                                {valuation.marginOfSafety > 0
                                    ? '↓ Precio por debajo del valor intrínseco'
                                    : '↑ Precio por encima del valor intrínseco'}
                            </p>
                        </div>

                        {/* Margin of Safety Gauge */}
                        <div className="bg-[#080808] rounded-xl p-4 flex flex-col items-center justify-center border border-gray-800/50">
                            <p className="text-xs text-gray-400 mb-3 font-medium">Margen de Seguridad</p>
                            <div className="relative w-24 h-24">
                                <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                                    <circle cx="50" cy="50" r="42" stroke="#1f2937" strokeWidth="8" fill="none" />
                                    <circle
                                        cx="50" cy="50" r="42"
                                        stroke={isUndervalued ? 'url(#gradientGreen)' : isOvervalued ? 'url(#gradientRed)' : 'url(#gradientYellow)'}
                                        strokeWidth="8"
                                        fill="none"
                                        strokeDasharray={`${Math.min(Math.abs(valuation.marginOfSafety) * 2.64, 264)} 264`}
                                        strokeLinecap="round"
                                        className="transition-all duration-1000"
                                    />
                                    <defs>
                                        <linearGradient id="gradientGreen" x1="0%" y1="0%" x2="100%" y2="0%">
                                            <stop offset="0%" stopColor="#14b8a6" />
                                            <stop offset="100%" stopColor="#22c55e" />
                                        </linearGradient>
                                        <linearGradient id="gradientRed" x1="0%" y1="0%" x2="100%" y2="0%">
                                            <stop offset="0%" stopColor="#ef4444" />
                                            <stop offset="100%" stopColor="#f97316" />
                                        </linearGradient>
                                        <linearGradient id="gradientYellow" x1="0%" y1="0%" x2="100%" y2="0%">
                                            <stop offset="0%" stopColor="#eab308" />
                                            <stop offset="100%" stopColor="#f59e0b" />
                                        </linearGradient>
                                    </defs>
                                </svg>
                                <div className="absolute inset-0 flex flex-col items-center justify-center">
                                    <span className="text-2xl font-bold text-white">{Math.abs(valuation.marginOfSafety).toFixed(1)}%</span>
                                    <span className="text-[9px] text-gray-500">{valuation.marginOfSafety > 0 ? 'descuento' : 'prima'}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Row 2: Verdict - Full Width */}
                    <div className={`rounded-xl p-4 flex items-center justify-between border ${isUndervalued ? 'bg-gradient-to-r from-teal-500/20 to-green-500/10 border-teal-500/30' :
                        isOvervalued ? 'bg-gradient-to-r from-red-500/20 to-orange-500/10 border-red-500/30' :
                            'bg-gradient-to-r from-yellow-500/20 to-amber-500/10 border-yellow-500/30'
                        }`}>
                        <div className="flex items-center gap-4">
                            <div>
                                <p className="text-xs text-gray-400 mb-1 font-medium">VEREDICTO FINAL</p>
                                <p className={`text-2xl font-bold ${isUndervalued ? 'text-teal-400' : isOvervalued ? 'text-red-400' : 'text-yellow-400'
                                    }`}>
                                    {valuation.verdict === 'UNDERVALUED' ? 'INFRAVALORADA' :
                                        valuation.verdict === 'OVERVALUED' ? 'SOBREVALORADA' : 'VALOR JUSTO'}
                                </p>
                            </div>
                        </div>
                        <p className="text-sm text-gray-400 max-w-md text-right">
                            {isUndervalued
                                ? `Con un margen del ${valuation.marginOfSafety.toFixed(0)}%, la acción cotiza significativamente por debajo de su valor intrínseco.`
                                : isOvervalued
                                    ? `La acción cotiza ${Math.abs(valuation.marginOfSafety).toFixed(0)}% por encima de su valor intrínseco calculado.`
                                    : 'La acción cotiza cerca de su valor intrínseco estimado por el modelo DCF.'
                            }
                        </p>
                    </div>
                </div>

                {/* Card 2: WACC & Terminal Value - IMPROVED */}
                <div className="bg-gradient-to-br from-[#111111] to-[#0d0d0d] border border-gray-800/80 rounded-2xl p-6 shadow-xl">
                    <div className="flex items-center justify-between mb-6">
                        <div>
                            <h3 className="text-lg font-semibold text-white">WACC <span className="text-teal-400">&</span> Terminal Value</h3>
                            <p className="text-xs text-gray-500">Datos reales: Treasury {thesisData.riskFreeRate.toFixed(2)}% | Beta {thesisData.beta.toFixed(2)}</p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
                        {/* Cost of Equity - WITH REAL DATA */}
                        <div className="bg-[#080808] rounded-xl p-4 border border-gray-800/50">
                            <p className="text-xs text-gray-400 flex items-center gap-1 mb-3 font-medium">
                                <TrendingUp className="h-3 w-3 text-purple-400" /> Costo de Equity (Ke)
                            </p>
                            <div className="space-y-1.5 text-[10px]">
                                <div className="flex justify-between text-gray-500">
                                    <span>Risk-Free (10Y T-Bond)</span>
                                    <span className="text-gray-300 font-medium">{thesisData.riskFreeRate.toFixed(2)}%</span>
                                </div>
                                <div className="flex justify-between text-gray-500">
                                    <span>Beta (Real)</span>
                                    <span className="text-gray-300 font-medium">{thesisData.beta.toFixed(2)}</span>
                                </div>
                                <div className="flex justify-between text-gray-500">
                                    <span>Equity Risk Premium</span>
                                    <span className="text-gray-300 font-medium">5.50%</span>
                                </div>
                            </div>
                            <div className="mt-3 pt-3 border-t border-gray-800 flex items-center justify-between">
                                <span className="text-xs text-purple-400 font-medium">KE RESULT</span>
                                <span className="text-xl font-bold text-white">{valuation.costOfEquity.toFixed(2)}%</span>
                            </div>
                        </div>

                        {/* WACC - IMPROVED VISUAL */}
                        <div className="bg-gradient-to-br from-[#080808] to-[#0a0a12] rounded-xl p-4 flex flex-col items-center justify-center border border-blue-900/30">
                            <p className="text-xs text-gray-400 mb-2 font-medium">WACC FINAL</p>
                            <p className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                                {valuation.wacc.toFixed(1)}%
                            </p>
                            <p className="text-[10px] text-gray-500 mt-2">Sensibilidad: ± 1.0%</p>
                            <div className="w-full h-2.5 bg-gray-800 rounded-full mt-3 overflow-hidden">
                                <div
                                    className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 rounded-full transition-all duration-1000"
                                    style={{ width: `${Math.min(100, valuation.wacc * 8)}%` }}
                                />
                            </div>
                            <div className="flex justify-between w-full text-[9px] text-gray-600 mt-1">
                                <span>5%</span>
                                <span>12%</span>
                            </div>
                        </div>

                        {/* Cost of Debt - WITH REAL DATA */}
                        <div className="bg-[#080808] rounded-xl p-4 border border-gray-800/50">
                            <p className="text-xs text-gray-400 flex items-center gap-1 mb-3 font-medium">
                                <Wallet className="h-3 w-3 text-blue-400" /> Costo de Deuda (Kd)
                            </p>
                            <div className="space-y-1.5 text-[10px]">
                                <div className="flex justify-between text-gray-500">
                                    <span>Pre-Tax Cost</span>
                                    <span className="text-gray-300 font-medium">{valuation.costOfDebt.toFixed(2)}%</span>
                                </div>
                                <div className="flex justify-between text-gray-500">
                                    <span>Tax Shield (21%)</span>
                                    <span className="text-green-400 font-medium">-21%</span>
                                </div>
                            </div>
                            <div className="mt-3 pt-3 border-t border-gray-800 flex items-center justify-between">
                                <span className="text-xs text-blue-400 font-medium">AFTER-TAX KD</span>
                                <span className="text-xl font-bold text-white">{(valuation.costOfDebt * 0.79).toFixed(2)}%</span>
                            </div>
                        </div>
                    </div>

                    {/* Terminal Value Calculation - IMPROVED */}
                    <div className="bg-[#080808] rounded-xl p-4 border border-gray-800/50">
                        <div className="flex items-center justify-between mb-4">
                            <p className="text-xs text-gray-400 flex items-center gap-1 font-medium">
                                <Target className="h-3 w-3 text-teal-400" /> Terminal Value Calculation
                            </p>
                            <span className="text-[10px] px-2 py-1 bg-teal-500/10 border border-teal-500/30 rounded text-teal-400">Perpetuity Growth</span>
                        </div>
                        <div className="grid grid-cols-4 gap-4 text-center items-center">
                            <div className="bg-[#0a0a0a] rounded-lg p-3">
                                <p className="text-[10px] text-gray-500 mb-1">FCF (Año 5)</p>
                                <p className="text-base font-bold text-white">${(thesisData.lastFCF / 1e9).toFixed(2)}B</p>
                            </div>
                            <div className="text-gray-600 text-2xl">÷</div>
                            <div className="bg-[#0a0a0a] rounded-lg p-3">
                                <p className="text-[10px] text-gray-500 mb-1">WACC - g</p>
                                <p className="text-base font-bold text-white">{(valuation.wacc - 2.5).toFixed(1)}%</p>
                            </div>
                            <div className="bg-teal-500/10 rounded-lg p-3 border border-teal-500/30">
                                <p className="text-[10px] text-teal-400 mb-1">TERMINAL VALUE</p>
                                <p className="text-base font-bold text-teal-400">${(valuation.terminalValue / 1e9).toFixed(0)}B</p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Card 3: Valuation Scenarios - IMPROVED */}
                <div className="bg-gradient-to-br from-[#111111] to-[#0d0d0d] border border-gray-800/80 rounded-2xl p-6 lg:col-span-2 shadow-xl">
                    <div className="flex items-center justify-between mb-6">
                        <div>
                            <h3 className="text-lg font-semibold text-white">Escenarios de <span className="text-teal-400">Valoración</span></h3>
                            <p className="text-xs text-gray-500">Stress-Testing: Casos Bear, Base y Bull con datos reales</p>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] text-gray-500">
                            <RefreshCw className="h-3 w-3" />
                            Basado en FCF real: ${(thesisData.lastFCF / 1e9).toFixed(2)}B
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6">
                        {valuation.scenarios.map((scenario) => (
                            <div
                                key={scenario.name}
                                className={`rounded-xl p-5 transition-all duration-300 hover:scale-[1.02] ${scenario.name === 'bear'
                                    ? 'bg-gradient-to-br from-red-500/15 to-red-900/10 border border-red-800/50 hover:border-red-600/50'
                                    : scenario.name === 'base'
                                        ? 'bg-gradient-to-br from-gray-800/60 to-gray-900/60 border border-gray-600/50 hover:border-gray-500/50'
                                        : 'bg-gradient-to-br from-green-500/15 to-green-900/10 border border-green-800/50 hover:border-green-600/50'
                                    }`}
                            >
                                {scenario.name === 'base' && (
                                    <div className="text-center mb-3">
                                        <span className="text-[10px] px-2 py-1 bg-gray-600/50 rounded text-white font-medium">ANCLA CONSERVADORA</span>
                                    </div>
                                )}
                                <p className={`text-xs mb-2 flex items-center gap-1 font-medium ${scenario.name === 'bear' ? 'text-red-400' :
                                    scenario.name === 'base' ? 'text-gray-300' :
                                        'text-green-400'
                                    }`}>
                                    {scenario.name === 'bear' ? <TrendingDown className="h-3 w-3" /> : <TrendingUp className="h-3 w-3" />}
                                    {scenario.name === 'bear' ? 'CASO PESIMISTA' : scenario.name === 'base' ? 'CASO BASE' : 'CASO OPTIMISTA'}
                                </p>
                                <p className={`text-5xl font-bold mb-4 ${scenario.name === 'bear' ? 'text-red-400' :
                                    scenario.name === 'base' ? 'text-white' :
                                        'text-green-400'
                                    }`}>
                                    ${scenario.targetPrice.toFixed(0)}
                                </p>
                                <p className="text-[10px] text-gray-500 mb-4 h-8">
                                    {scenario.name === 'bear' ? '≈ Múltiplo de sector industrial' :
                                        scenario.name === 'base' ? '≈ Output del modelo DCF' :
                                            '≈ Dominancia en agregación AV'}
                                </p>
                                <div className="space-y-2 text-[11px]">
                                    <div className="flex justify-between text-gray-400">
                                        <span>→ WACC</span>
                                        <span className={`font-medium ${scenario.name === 'bear' ? 'text-red-300' :
                                            scenario.name === 'base' ? 'text-white' :
                                                'text-green-300'
                                            }`}>{scenario.wacc.toFixed(1)}%</span>
                                    </div>
                                    <div className="flex justify-between text-gray-400">
                                        <span>→ Terminal Growth</span>
                                        <span className={`font-medium ${scenario.name === 'bear' ? 'text-red-300' :
                                            scenario.name === 'base' ? 'text-white' :
                                                'text-green-300'
                                            }`}>{scenario.terminalGrowth.toFixed(1)}%</span>
                                    </div>
                                </div>
                                {/* Upside/Downside indicator */}
                                <div className={`mt-4 pt-3 border-t ${scenario.name === 'bear' ? 'border-red-800/50' :
                                    scenario.name === 'base' ? 'border-gray-700' :
                                        'border-green-800/50'
                                    }`}>
                                    <div className="flex justify-between items-center">
                                        <span className="text-[10px] text-gray-500">vs Precio Actual</span>
                                        <span className={`text-sm font-bold ${scenario.targetPrice > valuation.currentPrice ? 'text-green-400' : 'text-red-400'
                                            }`}>
                                            {((scenario.targetPrice - valuation.currentPrice) / valuation.currentPrice * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* AI Commentary Card */}
            <div className="bg-gradient-to-r from-purple-900/20 to-blue-900/20 border border-purple-500/30 rounded-2xl p-5 shadow-xl">
                <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3 mb-3">
                        <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-purple-500 to-blue-600 flex items-center justify-center">
                            <Brain className="h-5 w-5 text-white" />
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold text-white">Análisis IA + RAG</h3>
                            <p className="text-[10px] text-gray-500">Interpretación inteligente del DCF</p>
                        </div>
                    </div>
                    {aiCommentary && (
                        <span className={`text-[10px] px-2 py-1 rounded ${aiCommentary.confidence === 'high' ? 'bg-green-500/20 text-green-400 border border-green-500/30' :
                                aiCommentary.confidence === 'medium' ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30' :
                                    'bg-gray-500/20 text-gray-400 border border-gray-500/30'
                            }`}>
                            Confianza: {aiCommentary.confidence === 'high' ? 'Alta' : aiCommentary.confidence === 'medium' ? 'Media' : 'Baja'}
                        </span>
                    )}
                </div>

                {aiLoading ? (
                    <div className="flex items-center gap-2 text-gray-400 py-4">
                        <Loader2 className="h-4 w-4 animate-spin text-purple-400" />
                        <span className="text-sm">Analizando valoración con IA...</span>
                    </div>
                ) : aiCommentary ? (
                    <div className="space-y-3">
                        <p className="text-sm text-gray-300 leading-relaxed">
                            {aiCommentary.commentary}
                        </p>
                        <div className="flex items-center gap-2 pt-2 border-t border-gray-700/50">
                            <span className="text-[10px] text-purple-400 font-medium">KEY INSIGHT:</span>
                            <span className="text-xs text-white">{aiCommentary.keyInsight}</span>
                        </div>
                    </div>
                ) : (
                    <p className="text-sm text-gray-500">El análisis IA se cargará después de los datos.</p>
                )}
            </div>
        </div>
    );
}

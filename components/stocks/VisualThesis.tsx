'use client';

import { useState, useEffect } from 'react';
import { Loader2, Sparkles, TrendingUp, TrendingDown, Target, Wallet, Brain, AlertTriangle, Info, RefreshCw, Newspaper } from 'lucide-react';
import { generateAIDrivenValuation, type AIValuationResult } from '@/lib/actions/ai.actions';
import {
    getDCF,
    getFundamentals,
    getKeyMetricsTTM,
    getEnterpriseValue,
    getTreasuryRates,
    getPriceTarget,
    getRatiosTTM,
    getPressReleases
} from '@/lib/actions/fmp.actions';
import { getProfile, getStockQuote, getCompanyNews } from '@/lib/actions/finnhub.actions';

interface VisualThesisProps {
    symbol: string;
    companyName: string;
    currentPrice: number;
}

export default function VisualThesis({ symbol, companyName, currentPrice }: VisualThesisProps) {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [aiValuation, setAiValuation] = useState<AIValuationResult | null>(null);
    const [apiContext, setApiContext] = useState<{ beta: number; riskFreeRate: number; lastFCF: number; newsCount: number } | null>(null);

    useEffect(() => {
        async function fetchAndAnalyze() {
            try {
                setLoading(true);
                setError(null);

                // 1. Fetch all API data (como CONTEXTO para la IA) + NOTICIAS
                const [dcfData, fundamentals, keyMetrics, evData, treasuryData, profile, quote, priceTarget, ratios, companyNews, pressReleases] = await Promise.all([
                    getDCF(symbol),
                    getFundamentals(symbol, 'annual'),
                    getKeyMetricsTTM(symbol),
                    getEnterpriseValue(symbol),
                    getTreasuryRates(),
                    getProfile(symbol),
                    getStockQuote(symbol),
                    getPriceTarget(symbol),
                    getRatiosTTM(symbol),
                    getCompanyNews(symbol, 10),           // Noticias de Finnhub
                    getPressReleases(symbol, 5)           // Press Releases de FMP
                ]);

                // Extract API values as CONTEXT
                const fmpDcf = dcfData?.dcf?.[0]?.dcf || null;
                const stockPrice = quote?.c || currentPrice;
                const realBeta = (profile as any)?.beta || 1.0;
                const sector = (profile as any)?.finnhubIndustry || 'Technology';
                const marketCap = evData?.enterpriseValue?.[0]?.marketCapitalization || 0;
                const riskFreeRate = treasuryData?.treasuryRates?.[0]?.year10 || 4.5;

                const km = keyMetrics?.keyMetrics?.[0];
                const debtToEquity = km?.debtToEquityTTM || 0.5;

                const cashflows = fundamentals?.cashflow || [];
                const lastFCF = cashflows[0]?.freeCashFlow || 0;

                const incomeStatements = fundamentals?.income || [];
                const revenueGrowth = incomeStatements.length >= 2
                    ? ((incomeStatements[0].revenue - incomeStatements[1].revenue) / incomeStatements[1].revenue) * 100
                    : 0;

                const analystTarget = priceTarget?.priceTarget?.[0]?.targetConsensus || null;

                const ratiosTTM = ratios?.ratios?.[0];
                const grossMargin = ratiosTTM?.grossProfitMarginTTM;
                const operatingMargin = ratiosTTM?.operatingProfitMarginTTM;
                const roe = ratiosTTM?.returnOnEquityTTM;

                // Procesar noticias para el contexto de la IA
                const finnhubNews = (companyNews || []).map((n: any) => ({
                    headline: n.headline || '',
                    summary: n.summary || '',
                    date: n.datetime ? new Date(n.datetime * 1000).toISOString().split('T')[0] : '',
                    source: n.source || 'Finnhub'
                }));

                const fmpNews = (pressReleases?.pressReleases || []).map((p: any) => ({
                    headline: p.title || '',
                    summary: p.text?.substring(0, 200) || '',
                    date: p.publishedDate?.split('T')[0] || '',
                    source: 'Press Release'
                }));

                const recentNews = [...finnhubNews, ...fmpNews]
                    .filter(n => n.headline)
                    .slice(0, 10);

                // Store context for display
                setApiContext({ beta: realBeta, riskFreeRate, lastFCF, newsCount: recentNews.length });

                // 2. Call AI to generate valuation (IA-FIRST approach) CON NOTICIAS
                const aiResult = await generateAIDrivenValuation({
                    symbol,
                    companyName,
                    currentPrice: stockPrice,
                    apiData: {
                        fmpDcf,
                        analystTarget,
                        fcfLastYear: lastFCF,
                        revenueGrowth,
                        marketCap,
                        beta: realBeta,
                        riskFreeRate,
                        debtToEquity,
                        sector,
                        grossMargin,
                        operatingMargin,
                        roe,
                        roic: km?.roicTTM,
                        recentNews  // NOTICIAS para contexto IA
                    }
                });

                setAiValuation(aiResult);

            } catch (err) {
                console.error('Error generating AI thesis:', err);
                setError('No se pudo generar el análisis de valoración');
            } finally {
                setLoading(false);
            }
        }

        fetchAndAnalyze();
    }, [symbol, companyName, currentPrice]);

    if (loading) {
        return (
            <div className="bg-gradient-to-br from-[#0a0a0a] to-[#111111] border border-gray-800 rounded-2xl p-8">
                <div className="flex items-center justify-center gap-3 text-gray-400">
                    <Loader2 className="h-6 w-6 animate-spin text-purple-500" />
                    <span>Generando valoración con IA...</span>
                </div>
                <p className="text-center text-xs text-gray-500 mt-2">Analizando datos de APIs y generando insights propios</p>
            </div>
        );
    }

    if (error || !aiValuation) {
        return (
            <div className="bg-red-900/20 border border-red-800 rounded-2xl p-6 text-red-300">
                {error || 'Error al generar el análisis'}
            </div>
        );
    }

    const { intrinsicValue, marginOfSafety, verdict, wacc, costOfEquity, scenarios, apiFeedback, reasoning, confidence, keyInsight, terminalValue } = aiValuation;
    const isUndervalued = verdict === 'UNDERVALUED';
    const isOvervalued = verdict === 'OVERVALUED';

    // Calculate bar heights
    const maxPrice = Math.max(currentPrice, intrinsicValue);
    const currentBarHeight = (currentPrice / maxPrice) * 70;
    const intrinsicBarHeight = (intrinsicValue / maxPrice) * 70;

    return (
        <div className="space-y-6">
            {/* Header - Always shows AI badge */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-purple-500/20">
                        <Brain className="h-5 w-5 text-white" />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-white">Valoración IA</h2>
                        <p className="text-sm text-gray-400">{companyName}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2 px-3 py-1.5 bg-purple-500/10 border border-purple-500/30 rounded-full">
                    <Brain className="h-3.5 w-3.5 text-purple-400" />
                    <span className="text-xs text-purple-400 font-medium">Análisis generado por IA</span>
                </div>
            </div>

            {/* AI Feedback about FMP DCF */}
            {apiFeedback.fmpDcf && apiFeedback.aiAgreement !== 'agree' && (
                <div className={`flex items-start gap-3 p-3 rounded-xl border ${apiFeedback.aiAgreement === 'disagree_low'
                    ? 'bg-orange-500/10 border-orange-500/30'
                    : 'bg-blue-500/10 border-blue-500/30'
                    }`}>
                    <Info className={`h-5 w-5 flex-shrink-0 mt-0.5 ${apiFeedback.aiAgreement === 'disagree_low' ? 'text-orange-400' : 'text-blue-400'
                        }`} />
                    <div>
                        <p className={`text-sm font-medium ${apiFeedback.aiAgreement === 'disagree_low' ? 'text-orange-300' : 'text-blue-300'
                            }`}>
                            DCF de FMP: ${apiFeedback.fmpDcf.toFixed(2)} → Ajustado a ${intrinsicValue.toFixed(2)}
                        </p>
                        <p className="text-xs text-gray-400 mt-1">{apiFeedback.adjustmentReason}</p>
                    </div>
                </div>
            )}

            {/* Card Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Card 1: Valuation Analysis */}
                <div className="bg-gradient-to-br from-[#111111] to-[#0d0d0d] border border-gray-800/80 rounded-2xl p-6 shadow-xl">
                    <div className="flex items-center justify-between mb-6">
                        <div>
                            <h3 className="text-lg font-semibold text-white">{symbol}: Valoración IA</h3>
                            <p className="text-xs text-gray-500">Estimación propia basada en análisis integral</p>
                        </div>
                        <div className={`px-2 py-1 rounded text-xs font-medium ${confidence === 'high' ? 'bg-green-500/20 text-green-400' :
                            confidence === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                                'bg-gray-500/20 text-gray-400'
                            }`}>
                            Confianza: {confidence === 'high' ? 'Alta' : confidence === 'medium' ? 'Media' : 'Baja'}
                        </div>
                    </div>

                    {/* Price Bars */}
                    <div className="grid grid-cols-2 gap-4 mb-4">
                        <div className="bg-[#080808] rounded-xl p-4 border border-gray-800/50">
                            <div className="flex items-end justify-center gap-6 h-24 mb-3">
                                <div className="flex flex-col items-center">
                                    <div
                                        className="w-14 bg-gradient-to-t from-teal-600 to-teal-400 rounded-t-md shadow-lg shadow-teal-500/30 transition-all duration-500"
                                        style={{ height: `${currentBarHeight}px` }}
                                    />
                                    <div className="mt-2 text-center">
                                        <p className="text-sm font-bold text-teal-400">${currentPrice.toFixed(2)}</p>
                                        <p className="text-[10px] text-gray-500">Precio Actual</p>
                                    </div>
                                </div>
                                <div className="flex flex-col items-center">
                                    <div
                                        className="w-14 bg-gradient-to-t from-purple-600 to-purple-400 rounded-t-md shadow-lg shadow-purple-500/30 transition-all duration-500"
                                        style={{ height: `${intrinsicBarHeight}px` }}
                                    />
                                    <div className="mt-2 text-center">
                                        <p className="text-sm font-bold text-purple-400">${intrinsicValue.toFixed(2)}</p>
                                        <p className="text-[10px] text-gray-500">Valor IA</p>
                                    </div>
                                </div>
                            </div>
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
                                        strokeDasharray={`${Math.min(Math.abs(marginOfSafety) * 2.64, 264)} 264`}
                                        strokeLinecap="round"
                                        className="transition-all duration-1000"
                                    />
                                    <defs>
                                        <linearGradient id="gradientGreen" x1="0%" y1="0%" x2="100%" y2="0%">
                                            <stop offset="0%" stopColor="#a855f7" />
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
                                    <span className="text-2xl font-bold text-white">{Math.abs(marginOfSafety).toFixed(1)}%</span>
                                    <span className="text-[9px] text-gray-500">{marginOfSafety > 0 ? 'descuento' : 'prima'}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Verdict */}
                    <div className={`rounded-xl p-4 flex items-center justify-between border ${isUndervalued ? 'bg-gradient-to-r from-purple-500/20 to-green-500/10 border-purple-500/30' :
                        isOvervalued ? 'bg-gradient-to-r from-red-500/20 to-orange-500/10 border-red-500/30' :
                            'bg-gradient-to-r from-yellow-500/20 to-amber-500/10 border-yellow-500/30'
                        }`}>
                        <div>
                            <p className="text-xs text-gray-400 mb-1 font-medium">VEREDICTO IA</p>
                            <p className={`text-2xl font-bold ${isUndervalued ? 'text-purple-400' : isOvervalued ? 'text-red-400' : 'text-yellow-400'
                                }`}>
                                {verdict === 'UNDERVALUED' ? 'INFRAVALORADA' :
                                    verdict === 'OVERVALUED' ? 'SOBREVALORADA' : 'VALOR JUSTO'}
                            </p>
                        </div>
                        <p className="text-sm text-gray-400 max-w-md text-right">
                            {isUndervalued
                                ? `La IA estima un potencial del ${marginOfSafety.toFixed(0)}% vs precio actual.`
                                : isOvervalued
                                    ? `La IA considera que cotiza ${Math.abs(marginOfSafety).toFixed(0)}% por encima de su valor.`
                                    : 'La IA considera que cotiza cerca de su valor intrínseco.'
                            }
                        </p>
                    </div>
                </div>

                {/* Card 2: WACC & Scenarios */}
                <div className="bg-gradient-to-br from-[#111111] to-[#0d0d0d] border border-gray-800/80 rounded-2xl p-6 shadow-xl">
                    <div className="flex items-center justify-between mb-6">
                        <div>
                            <h3 className="text-lg font-semibold text-white">Parámetros <span className="text-purple-400">IA</span></h3>
                            <p className="text-xs text-gray-500">
                                Datos base: Treasury {apiContext?.riskFreeRate.toFixed(2)}% | Beta {apiContext?.beta.toFixed(2)}
                            </p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
                        {/* WACC */}
                        <div className="bg-gradient-to-br from-[#080808] to-[#0a0a12] rounded-xl p-4 flex flex-col items-center justify-center border border-purple-900/30">
                            <p className="text-xs text-gray-400 mb-2 font-medium">WACC IA</p>
                            <p className="text-3xl font-bold bg-gradient-to-r from-purple-400 to-indigo-400 bg-clip-text text-transparent">
                                {wacc.toFixed(1)}%
                            </p>
                        </div>

                        {/* Cost of Equity */}
                        <div className="bg-[#080808] rounded-xl p-4 flex flex-col items-center justify-center border border-gray-800/50">
                            <p className="text-xs text-gray-400 mb-2 font-medium">Costo Equity</p>
                            <p className="text-3xl font-bold text-white">{costOfEquity.toFixed(1)}%</p>
                        </div>

                        {/* Terminal Value */}
                        <div className="bg-[#080808] rounded-xl p-4 flex flex-col items-center justify-center border border-gray-800/50">
                            <p className="text-xs text-gray-400 mb-2 font-medium">Terminal Value</p>
                            <p className="text-3xl font-bold text-teal-400">${(terminalValue / 1e9).toFixed(0)}B</p>
                        </div>
                    </div>

                    {/* AI Reasoning */}
                    <div className="bg-purple-900/20 rounded-xl p-4 border border-purple-500/30">
                        <p className="text-sm text-gray-300 leading-relaxed">{reasoning}</p>
                        {keyInsight && (
                            <div className="flex items-center gap-2 pt-3 mt-3 border-t border-purple-500/30">
                                <span className="text-[10px] text-purple-400 font-medium">KEY INSIGHT:</span>
                                <span className="text-xs text-white">{keyInsight}</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* Card 3: Scenarios */}
                <div className="bg-gradient-to-br from-[#111111] to-[#0d0d0d] border border-gray-800/80 rounded-2xl p-6 lg:col-span-2 shadow-xl">
                    <div className="flex items-center justify-between mb-6">
                        <div>
                            <h3 className="text-lg font-semibold text-white">Escenarios <span className="text-purple-400">IA</span></h3>
                            <p className="text-xs text-gray-500">Proyecciones generadas por análisis IA</p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6">
                        {[
                            { name: 'bear', label: 'CASO PESIMISTA', data: scenarios.bear, color: 'red' },
                            { name: 'base', label: 'CASO BASE', data: scenarios.base, color: 'gray' },
                            { name: 'bull', label: 'CASO OPTIMISTA', data: scenarios.bull, color: 'green' }
                        ].map((scenario) => (
                            <div
                                key={scenario.name}
                                className={`rounded-xl p-5 transition-all duration-300 hover:scale-[1.02] ${scenario.name === 'bear'
                                    ? 'bg-gradient-to-br from-red-500/15 to-red-900/10 border border-red-800/50'
                                    : scenario.name === 'base'
                                        ? 'bg-gradient-to-br from-purple-500/15 to-purple-900/10 border border-purple-500/50'
                                        : 'bg-gradient-to-br from-green-500/15 to-green-900/10 border border-green-800/50'
                                    }`}
                            >
                                <p className={`text-xs mb-2 flex items-center gap-1 font-medium ${scenario.name === 'bear' ? 'text-red-400' :
                                    scenario.name === 'base' ? 'text-purple-300' :
                                        'text-green-400'
                                    }`}>
                                    {scenario.name === 'bear' ? <TrendingDown className="h-3 w-3" /> : <TrendingUp className="h-3 w-3" />}
                                    {scenario.label}
                                </p>
                                <p className={`text-4xl font-bold mb-2 ${scenario.name === 'bear' ? 'text-red-400' :
                                    scenario.name === 'base' ? 'text-purple-400' :
                                        'text-green-400'
                                    }`}>
                                    ${scenario.data.price.toFixed(0)}
                                </p>
                                <p className="text-[10px] text-gray-500 mb-3">
                                    Probabilidad: {scenario.data.probability}%
                                </p>
                                <div className={`pt-3 border-t ${scenario.name === 'bear' ? 'border-red-800/50' :
                                    scenario.name === 'base' ? 'border-purple-700/50' :
                                        'border-green-800/50'
                                    }`}>
                                    <div className="flex justify-between items-center">
                                        <span className="text-[10px] text-gray-500">vs Precio Actual</span>
                                        <span className={`text-sm font-bold ${scenario.data.price > currentPrice ? 'text-green-400' : 'text-red-400'
                                            }`}>
                                            {((scenario.data.price - currentPrice) / currentPrice * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}

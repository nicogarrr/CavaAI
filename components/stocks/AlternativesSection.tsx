'use client';

import { useState, useEffect } from 'react';
import { getAlternativeSuggestions } from '@/lib/actions/ai.actions';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';
import { ArrowRight, TrendingUp, TrendingDown, CheckCircle, AlertTriangle, RefreshCw, Loader2 } from 'lucide-react';

interface AlternativesSectionProps {
    symbol: string;
    companyName: string;
    sector?: string;
    financialData: any;
    currentPrice: number;
}

export default function AlternativesSection({
    symbol,
    companyName,
    sector,
    financialData,
    currentPrice
}: AlternativesSectionProps) {
    const [loading, setLoading] = useState(true);
    const [result, setResult] = useState<{
        currentStock: { symbol: string; name: string; score: number; strengths: string[]; weaknesses: string[] };
        alternatives: { symbol: string; name: string; score: number; reason: string; isBetter: boolean }[];
        recommendation: string;
        summary: string;
    } | null>(null);

    const loadAnalysis = async () => {
        setLoading(true);
        try {
            const data = await getAlternativeSuggestions({
                symbol,
                companyName,
                sector,
                financialData,
                currentPrice
            });
            setResult(data);
        } catch (error) {
            console.error('Error loading alternatives:', error);
        }
        setLoading(false);
    };

    // Auto-execute on mount
    useEffect(() => {
        loadAnalysis();
    }, [symbol]);

    const getRecommendationStyle = (rec: string) => {
        if (rec === 'MEJOR_OPCION') return { bg: 'bg-green-600', icon: CheckCircle, text: 'Mejor Opción del Sector' };
        if (rec === 'MANTENER') return { bg: 'bg-blue-600', icon: CheckCircle, text: 'Buena Opción - Mantener' };
        if (rec === 'CONSIDERAR_ALTERNATIVAS') return { bg: 'bg-yellow-600', icon: AlertTriangle, text: 'Considerar Alternativas' };
        return { bg: 'bg-gray-600', icon: CheckCircle, text: rec };
    };

    if (loading) {
        return (
            <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6">
                <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-8 w-8 animate-spin text-teal-500" />
                    <span className="ml-3 text-gray-400">Analizando competidores del sector...</span>
                </div>
            </div>
        );
    }

    if (!result) {
        return (
            <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6">
                <p className="text-gray-400">No se pudo cargar el análisis de alternativas</p>
            </div>
        );
    }

    const recStyle = getRecommendationStyle(result?.recommendation || '');

    return (
        <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-white">Análisis de Alternativas - {symbol}</h2>
                <Button onClick={loadAnalysis} variant="outline" size="sm">
                    <RefreshCw className="h-4 w-4 mr-1" /> Regenerar
                </Button>
            </div>

            {/* Recommendation Badge */}
            <div className="flex items-center gap-4">
                <Badge className={`${recStyle.bg} text-white px-4 py-2 text-sm`}>
                    {recStyle.text}
                </Badge>
            </div>

            {/* Summary */}
            <div className="p-4 bg-gray-900 rounded-lg">
                <p className="text-gray-300">{result?.summary}</p>
            </div>

            {/* Current Stock Score */}
            <div className="p-4 bg-gray-900 rounded-lg">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-white">{symbol} - Tu Selección</h3>
                    <div className="text-3xl font-bold text-teal-400">{result?.currentStock.score}/100</div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                    {/* Strengths */}
                    <div>
                        <h4 className="text-sm text-green-400 mb-2 flex items-center gap-1">
                            <TrendingUp className="w-4 h-4" /> Fortalezas
                        </h4>
                        <ul className="space-y-1">
                            {result?.currentStock.strengths.map((s, i) => (
                                <li key={i} className="text-sm text-gray-300 flex items-start gap-2">
                                    <span className="text-green-400">+</span> {s}
                                </li>
                            ))}
                        </ul>
                    </div>

                    {/* Weaknesses */}
                    <div>
                        <h4 className="text-sm text-red-400 mb-2 flex items-center gap-1">
                            <TrendingDown className="w-4 h-4" /> Debilidades
                        </h4>
                        <ul className="space-y-1">
                            {result?.currentStock.weaknesses.map((w, i) => (
                                <li key={i} className="text-sm text-gray-300 flex items-start gap-2">
                                    <span className="text-red-400">-</span> {w}
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>
            </div>

            {/* Alternatives */}
            {result?.alternatives && result.alternatives.length > 0 && (
                <div>
                    <h3 className="text-lg font-semibold text-white mb-3">Competidores del Sector</h3>
                    <div className="space-y-3">
                        {result.alternatives.map((alt, i) => (
                            <Link
                                key={i}
                                href={`/stocks/${alt.symbol}`}
                                className="block p-4 bg-gray-900 rounded-lg hover:bg-gray-800 transition-colors"
                            >
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        {alt.isBetter ? (
                                            <Badge className="bg-green-600">Mejor</Badge>
                                        ) : (
                                            <Badge className="bg-gray-600">Similar</Badge>
                                        )}
                                        <div>
                                            <span className="text-white font-semibold">{alt.symbol}</span>
                                            <span className="text-gray-400 text-sm ml-2">{alt.name}</span>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-4">
                                        <span className={`text-xl font-bold ${alt.isBetter ? 'text-green-400' : 'text-gray-300'}`}>
                                            {alt.score}/100
                                        </span>
                                        <ArrowRight className="w-5 h-5 text-gray-500" />
                                    </div>
                                </div>
                                <p className="text-sm text-gray-400 mt-2">{alt.reason}</p>
                            </Link>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

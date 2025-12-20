'use client';

import { useState, useEffect } from 'react';
import { generatePatternAnalysis } from '@/lib/actions/ai.actions';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface PatternAnalysisSectionProps {
    symbol: string;
    companyName: string;
    financialData: any;
    currentPrice: number;
}

interface Pattern {
    name: string;
    type: 'bullish' | 'bearish' | 'neutral';
    confidence: number;
    description: string;
    priceTarget?: number;
}

export default function PatternAnalysisSection({
    symbol,
    companyName,
    financialData,
    currentPrice
}: PatternAnalysisSectionProps) {
    const [loading, setLoading] = useState(true);
    const [result, setResult] = useState<{
        patterns: Pattern[];
        elliottWave: { currentWave: string; position: string; nextMove: string; confidence: number };
        supportResistance: { supports: number[]; resistances: number[]; keyLevel: number; trend: string };
        summary: string;
    } | null>(null);

    const loadAnalysis = async () => {
        setLoading(true);
        try {
            const data = await generatePatternAnalysis({
                symbol,
                companyName,
                currentPrice
            });
            setResult(data);
        } catch (error) {
            console.error('Error loading pattern analysis:', error);
        }
        setLoading(false);
    };

    // Auto-execute on mount
    useEffect(() => {
        loadAnalysis();
    }, [symbol]);

    const getTypeColor = (type: string) => {
        if (type === 'bullish') return 'bg-green-600';
        if (type === 'bearish') return 'bg-red-600';
        return 'bg-gray-600';
    };

    const getTypeIcon = (type: string) => {
        if (type === 'bullish') return <TrendingUp className="h-5 w-5 text-green-400" />;
        if (type === 'bearish') return <TrendingDown className="h-5 w-5 text-red-400" />;
        return <Minus className="h-5 w-5 text-gray-400" />;
    };

    const getTrendColor = (trend: string) => {
        if (trend === 'bullish') return 'text-green-400';
        if (trend === 'bearish') return 'text-red-400';
        return 'text-yellow-400';
    };

    if (loading) {
        return (
            <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6">
                <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
                    <span className="ml-3 text-gray-400">Analizando patrones técnicos...</span>
                </div>
            </div>
        );
    }

    if (!result) {
        return (
            <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6">
                <p className="text-gray-400">No se pudo cargar el análisis de patrones</p>
            </div>
        );
    }

    return (
        <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-white">Análisis Técnico</h2>
                <Button onClick={loadAnalysis} variant="outline" size="sm">
                    <RefreshCw className="h-4 w-4 mr-1" /> Regenerar
                </Button>
            </div>

            {/* Summary */}
            <div className="p-4 bg-gray-900 rounded-lg">
                <p className="text-gray-300">{result?.summary}</p>
            </div>

            {/* Grid Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Elliott Wave */}
                <div className="p-4 bg-gray-900 rounded-lg">
                    <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                        Ondas de Elliott
                    </h3>
                    <div className="space-y-2">
                        <div className="flex justify-between">
                            <span className="text-gray-400">Onda actual:</span>
                            <span className="text-white font-bold text-xl">{result?.elliottWave.currentWave}</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-gray-400">Posición:</span>
                            <span className="text-gray-200">{result?.elliottWave.position}</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-gray-400">Próximo movimiento:</span>
                            <span className="text-gray-200">{result?.elliottWave.nextMove}</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-gray-400">Confianza:</span>
                            <span className="text-purple-400">{result?.elliottWave.confidence}%</span>
                        </div>
                    </div>
                </div>

                {/* Support/Resistance */}
                <div className="p-4 bg-gray-900 rounded-lg">
                    <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                        Soportes y Resistencias
                    </h3>
                    <div className="space-y-3">
                        <div className="flex justify-between items-center">
                            <span className="text-gray-400">Tendencia:</span>
                            <span className={`font-bold ${getTrendColor(result?.supportResistance.trend || '')}`}>
                                {result?.supportResistance.trend === 'bullish' ? 'Alcista' :
                                    result?.supportResistance.trend === 'bearish' ? 'Bajista' : 'Lateral'}
                            </span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-gray-400">Nivel clave:</span>
                            <span className="text-yellow-400 font-bold">${result?.supportResistance.keyLevel?.toFixed(2)}</span>
                        </div>
                        <div>
                            <span className="text-gray-400 text-sm">Resistencias:</span>
                            <div className="flex gap-2 mt-1 flex-wrap">
                                {result?.supportResistance.resistances?.map((r, i) => (
                                    <Badge key={i} className="bg-red-900/50 text-red-300">${r?.toFixed(2)}</Badge>
                                ))}
                                {(!result?.supportResistance.resistances?.length) && <span className="text-gray-500">N/A</span>}
                            </div>
                        </div>
                        <div>
                            <span className="text-gray-400 text-sm">Soportes:</span>
                            <div className="flex gap-2 mt-1 flex-wrap">
                                {result?.supportResistance.supports?.map((s, i) => (
                                    <Badge key={i} className="bg-green-900/50 text-green-300">${s?.toFixed(2)}</Badge>
                                ))}
                                {(!result?.supportResistance.supports?.length) && <span className="text-gray-500">N/A</span>}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Patterns */}
            {result?.patterns && result.patterns.length > 0 && (
                <div>
                    <h3 className="text-lg font-semibold text-white mb-3">Patrones Detectados</h3>
                    <div className="space-y-3">
                        {result.patterns.map((pattern, i) => (
                            <div key={i} className="p-4 bg-gray-900 rounded-lg flex items-start gap-4">
                                {getTypeIcon(pattern.type)}
                                <div className="flex-1">
                                    <div className="flex items-center gap-2">
                                        <span className="text-white font-semibold">{pattern.name}</span>
                                        <Badge className={getTypeColor(pattern.type)}>
                                            {pattern.type === 'bullish' ? 'Alcista' : pattern.type === 'bearish' ? 'Bajista' : 'Neutral'}
                                        </Badge>
                                        <span className="text-gray-400 text-sm">({pattern.confidence}% confianza)</span>
                                    </div>
                                    <p className="text-gray-400 text-sm mt-1">{pattern.description}</p>
                                    {pattern.priceTarget && (
                                        <p className="text-yellow-400 text-sm mt-1">
                                            Objetivo: ${pattern.priceTarget.toFixed(2)}
                                        </p>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

'use client';

import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';
import { TrendingUp, Sparkles, ArrowRight, Loader2, RefreshCw, Clock } from 'lucide-react';
import EnhancedProPicksFilters, { ProPicksFilters } from './EnhancedProPicksFilters';
import { generateEnhancedProPicks, type ProPick } from '@/lib/actions/proPicks.actions';

interface EnhancedProPicksContentProps {
    initialPicks: ProPick[];
    generatedAt?: string;
}

export default function EnhancedProPicksContent({ initialPicks, generatedAt }: EnhancedProPicksContentProps) {
    const [picks, setPicks] = useState<ProPick[]>(initialPicks);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [lastGenerated, setLastGenerated] = useState<string | null>(generatedAt || null);
    const [filters, setFilters] = useState<ProPicksFilters>({
        timePeriod: 'month',
        limit: 20,
        minScore: 70,
        sector: 'all',
        sortBy: 'score',
    });

    const handleApplyFilters = async () => {
        setLoading(true);
        setError(null);
        try {
            const newPicks = await generateEnhancedProPicks(filters);
            setPicks(newPicks);
            setLastGenerated(new Date().toISOString());
        } catch (error) {
            console.error('Error applying filters:', error);
            setError('Error al aplicar los filtros. Por favor, intenta de nuevo.');
        } finally {
            setLoading(false);
        }
    };

    const handleRefresh = async () => {
        setLoading(true);
        setError(null);
        try {
            const newPicks = await generateEnhancedProPicks(filters);
            setPicks(newPicks);
            setLastGenerated(new Date().toISOString());
        } catch (error) {
            console.error('Error refreshing picks:', error);
            setError('Error al regenerar. Por favor, intenta de nuevo.');
        } finally {
            setLoading(false);
        }
    };

    const formatLastGenerated = (isoString: string | null) => {
        if (!isoString) return null;
        const date = new Date(isoString);
        return date.toLocaleString('es-ES', {
            day: 'numeric',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    const getScoreColor = (score: number) => {
        if (score >= 80) return 'text-green-400 bg-green-500/10 border-green-500/20';
        if (score >= 70) return 'text-teal-400 bg-teal-500/10 border-teal-500/20';
        return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20';
    };

    const getGradeColor = (grade: string) => {
        if (grade.startsWith('A')) return 'bg-green-500';
        if (grade.startsWith('B')) return 'bg-teal-500';
        return 'bg-yellow-500';
    };

    const timePeriodLabels = {
        week: 'Semana',
        month: 'Mes',
        quarter: 'Trimestre',
        year: 'Año'
    };

    return (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            {/* Sidebar con filtros */}
            <div className="lg:col-span-1">
                <EnhancedProPicksFilters
                    filters={filters}
                    onFiltersChange={setFilters}
                    onApply={handleApplyFilters}
                />

                {/* Refresh Button */}
                <Card className="mt-4 p-4 border-gray-700 bg-gray-800/50">
                    <Button
                        onClick={handleRefresh}
                        disabled={loading}
                        className="w-full gap-2 bg-teal-600 hover:bg-teal-700"
                    >
                        {loading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <RefreshCw className="h-4 w-4" />
                        )}
                        Regenerar Picks
                    </Button>
                    {lastGenerated && (
                        <div className="mt-3 flex items-center gap-2 text-xs text-gray-500">
                            <Clock className="h-3 w-3" />
                            Generado: {formatLastGenerated(lastGenerated)}
                        </div>
                    )}
                </Card>

                {/* Info Card */}
                <Card className="mt-4 p-4 border-gray-700 bg-gray-800/50">
                    <h3 className="text-sm font-semibold text-gray-200 mb-2">
                        Sobre ProPicks IA
                    </h3>
                    <p className="text-xs text-gray-400 leading-relaxed">
                        Nuestro sistema analiza más de 100 métricas financieras,
                        compara cada acción con su sector y utiliza inteligencia artificial
                        para seleccionar las mejores oportunidades del mercado.
                    </p>
                    <div className="mt-3 pt-3 border-t border-gray-700">
                        <div className="text-xs text-gray-500 space-y-1">
                            <div>✓ Análisis fundamental avanzado</div>
                            <div>✓ Comparación con sector</div>
                            <div>✓ Evaluación de momentum</div>
                            <div>✓ Análisis de salud financiera</div>
                        </div>
                    </div>
                </Card>
            </div>

            {/* Resultados */}
            <div className="lg:col-span-3">
                {/* Header */}
                <div className="mb-6">
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                            <Badge variant="outline" className="text-teal-400 border-teal-400">
                                Top {picks.length}
                            </Badge>
                            <span className="text-sm text-gray-400">
                                {timePeriodLabels[filters.timePeriod]}
                            </span>
                        </div>
                        {loading && (
                            <div className="flex items-center gap-2 text-sm text-gray-400">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                Procesando...
                            </div>
                        )}
                    </div>
                    <p className="text-sm text-gray-400">
                        Acciones seleccionadas con score mínimo de {filters.minScore} ordenadas por {
                            filters.sortBy === 'score' ? 'score general' :
                                filters.sortBy === 'momentum' ? 'momentum' :
                                    filters.sortBy === 'value' ? 'valor' :
                                        filters.sortBy === 'growth' ? 'crecimiento' :
                                            'rentabilidad'
                        }
                    </p>
                </div>

                {error && (
                    <Card className="p-6 rounded-lg border border-red-700 bg-red-900/20 mb-4">
                        <p className="text-red-400 text-center">{error}</p>
                    </Card>
                )}

                {picks.length === 0 ? (
                    <Card className="p-8 rounded-lg border border-gray-700 bg-gray-800/50 text-center">
                        <Sparkles className="h-12 w-12 mx-auto mb-4 text-gray-600" />
                        <p className="text-gray-500">
                            No se encontraron acciones con los filtros seleccionados
                        </p>
                        <p className="text-sm text-gray-600 mt-2">
                            Intenta ajustar los criterios o haz clic en "Regenerar Picks"
                        </p>
                    </Card>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {picks.map((pick, index) => (
                            <Link
                                key={pick.symbol}
                                href={`/stocks/${pick.symbol}`}
                                className="block"
                            >
                                <Card className="p-5 rounded-lg border border-gray-700 bg-gray-800/50 hover:bg-gray-800 transition-all duration-200 group h-full">
                                    <div className="flex items-start justify-between mb-3">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2 mb-1">
                                                <span className="text-xs font-bold text-gray-500 px-2 py-1 bg-gray-900 rounded">
                                                    #{index + 1}
                                                </span>
                                                <h3 className="text-lg font-bold text-gray-100 group-hover:text-teal-400 transition-colors">
                                                    {pick.symbol}
                                                </h3>
                                                {pick.isStrongBuy && (
                                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold text-white bg-gradient-to-r from-teal-500 to-emerald-500 animate-pulse">
                                                        💎 JOYA
                                                    </span>
                                                )}
                                                {!pick.isStrongBuy && (
                                                    <span className={`px-2 py-0.5 rounded text-xs font-bold text-white ${getGradeColor(pick.grade)}`}>
                                                        {pick.grade}
                                                    </span>
                                                )}
                                            </div>
                                            <p className="text-sm text-gray-400 line-clamp-1">{pick.company}</p>
                                            {pick.sector && (
                                                <p className="text-xs text-gray-500 mt-1">{pick.sector}</p>
                                            )}
                                        </div>
                                        <div className={`text-right px-3 py-2 rounded-lg border ${getScoreColor(pick.score)}`}>
                                            <div className="text-2xl font-bold">
                                                {pick.score}
                                            </div>
                                            <div className="text-xs">Score</div>
                                        </div>
                                    </div>

                                    <div className="flex items-center justify-between mb-3">
                                        {pick.currentPrice > 0 && (
                                            <div>
                                                <div className="text-xl font-semibold text-gray-100">
                                                    ${pick.currentPrice.toFixed(2)}
                                                </div>
                                                <div className="text-xs text-gray-500">Precio actual</div>
                                            </div>
                                        )}
                                        {pick.upsidePotential && pick.upsidePotential > 0 && (
                                            <div className="text-right">
                                                <div className={`text-xl font-bold ${pick.upsidePotential > 15 ? 'text-emerald-400' : 'text-green-400'}`}>
                                                    +{pick.upsidePotential.toFixed(1)}%
                                                </div>
                                                <div className="text-xs text-gray-500">Potencial (12m)</div>
                                            </div>
                                        )}
                                    </div>

                                    {/* Category Scores */}
                                    <div className="grid grid-cols-3 gap-2 mb-3">
                                        <div className="text-center">
                                            <div className="text-xs text-gray-500">Valor</div>
                                            <div className={`text-sm font-semibold ${pick.categoryScores.value >= 70 ? 'text-green-400' : 'text-gray-400'}`}>
                                                {pick.categoryScores.value}
                                            </div>
                                        </div>
                                        <div className="text-center">
                                            <div className="text-xs text-gray-500">Momentum</div>
                                            <div className={`text-sm font-semibold ${pick.categoryScores.momentum >= 70 ? 'text-green-400' : 'text-gray-400'}`}>
                                                {pick.categoryScores.momentum}
                                            </div>
                                        </div>
                                        <div className="text-center">
                                            <div className="text-xs text-gray-500">Rentab.</div>
                                            <div className={`text-sm font-semibold ${pick.categoryScores.profitability >= 70 ? 'text-green-400' : 'text-gray-400'}`}>
                                                {pick.categoryScores.profitability}
                                            </div>
                                        </div>
                                    </div>

                                    {pick.reasons.length > 0 && (
                                        <div className="space-y-1.5 mb-3">
                                            {pick.reasons.slice(0, 2).map((reason, reasonIndex) => (
                                                <div key={reasonIndex} className="flex items-start gap-2 text-xs text-gray-300">
                                                    <TrendingUp className="h-3 w-3 text-teal-400 flex-shrink-0 mt-0.5" />
                                                    <span className="line-clamp-1">{reason}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    <div className="flex items-center justify-end pt-3 border-t border-gray-700 mt-auto">
                                        <Button variant="ghost" size="sm" className="gap-2 text-gray-400 group-hover:text-teal-400 h-8 text-xs">
                                            Ver análisis completo
                                            <ArrowRight className="h-3 w-3" />
                                        </Button>
                                    </div>
                                </Card>
                            </Link>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

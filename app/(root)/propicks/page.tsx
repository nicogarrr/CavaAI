import { generateProPicks, getAvailableStrategies } from '@/lib/actions/proPicks.actions';
import { Card } from '@/components/ui/card';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { TrendingUp, Sparkles, ArrowRight } from 'lucide-react';
import StrategySelector from '@/components/proPicks/StrategySelector';

// Forzar renderizado dinámico porque requiere datos en tiempo real
export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function ProPicksPage({ 
    searchParams 
}: { 
    searchParams?: { strategy?: string } 
}) {
    const strategyId = searchParams?.strategy || 'beat-sp500';
    const picks = await generateProPicks(20, strategyId);
    const strategies = await getAvailableStrategies();

    const currentMonth = new Date().toLocaleDateString('es-ES', { month: 'long', year: 'numeric' });

    return (
        <div className="flex min-h-screen flex-col p-6">
            <div className="mb-8">
                <div className="flex items-center gap-3 mb-4">
                    <Sparkles className="h-8 w-8 text-teal-400" />
                    <div>
                        <h1 className="text-3xl font-bold text-gray-100">ProPicks IA</h1>
                        <p className="text-gray-400 mt-1">
                            Acciones seleccionadas por nuestra inteligencia artificial para {currentMonth}
                        </p>
                    </div>
                </div>
                <p className="text-gray-300 max-w-3xl mb-4">
                    Nuestra IA analiza miles de acciones usando más de 100 métricas financieras comparándolas 
                    siempre contra sus pares del sector. Motor de análisis multifactorial que pondera Valor, 
                    Crecimiento, Rentabilidad, Flujo de Caja, Impulso y Deuda/Liquidez.
                </p>

                {/* Selector de estrategias */}
                <StrategySelector strategies={strategies} currentStrategy={strategyId} />
            </div>

            {picks.length === 0 ? (
                <Card className="p-8 rounded-lg border border-gray-700 bg-gray-800/50 text-center">
                    <Sparkles className="h-12 w-12 mx-auto mb-4 text-gray-600" />
                    <p className="text-gray-500">No hay picks disponibles en este momento.</p>
                </Card>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {picks.map((pick, index) => {
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

                        return (
                            <Link
                                key={pick.symbol}
                                href={`/stocks/${pick.symbol}`}
                                className="block"
                            >
                                <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50 hover:bg-gray-800 transition-all duration-200 group h-full">
                                    <div className="flex items-start justify-between mb-4">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2 mb-1">
                                                <span className="text-xs font-bold text-gray-500 px-2 py-1 bg-gray-900 rounded">
                                                    #{index + 1}
                                                </span>
                                                <h3 className="text-xl font-bold text-gray-100 group-hover:text-teal-400 transition-colors">
                                                    {pick.symbol}
                                                </h3>
                                                <span className={`px-2 py-0.5 rounded text-xs font-bold text-white ${getGradeColor(pick.grade)}`}>
                                                    {pick.grade}
                                                </span>
                                            </div>
                                            <p className="text-sm text-gray-400 line-clamp-1">{pick.company}</p>
                                        </div>
                                        <div className={`text-right px-4 py-2 rounded-lg border ${getScoreColor(pick.score)}`}>
                                            <div className="text-3xl font-bold">
                                                {pick.score}
                                            </div>
                                            <div className="text-xs">Score</div>
                                        </div>
                                    </div>
                                    
                                    {pick.currentPrice > 0 && (
                                        <div className="mb-4">
                                            <div className="text-2xl font-semibold text-gray-100">
                                                ${pick.currentPrice.toFixed(2)}
                                            </div>
                                            <div className="text-xs text-gray-500">Precio actual</div>
                                        </div>
                                    )}

                                    {pick.reasons.length > 0 && (
                                        <div className="space-y-2 mb-4">
                                            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                                                Por qué esta acción
                                            </h4>
                                            {pick.reasons.map((reason, reasonIndex) => (
                                                <div key={reasonIndex} className="flex items-start gap-2 text-sm text-gray-300">
                                                    <TrendingUp className="h-4 w-4 text-teal-400 flex-shrink-0 mt-0.5" />
                                                    <span>{reason}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    <div className="flex items-center justify-end pt-4 border-t border-gray-700 mt-auto">
                                        <Button variant="ghost" size="sm" className="gap-2 text-gray-400 group-hover:text-teal-400">
                                            Ver detalles
                                            <ArrowRight className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </Card>
                            </Link>
                        );
                    })}
                </div>
            )}
        </div>
    );
}


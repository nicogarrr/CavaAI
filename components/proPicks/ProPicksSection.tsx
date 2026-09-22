import { generateProPicks, type ProPick } from '@/lib/actions/proPicks.actions';
import { SCORING_WEIGHTS } from '@/lib/utils/advancedStockScoring';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { ArrowRight, TrendingUp, Sparkles } from 'lucide-react';

export default async function ProPicksSection() {
    // Manejar errores silenciosamente para evitar fallos en build
    let picks: ProPick[] = [];
    try {
        // Usar estrategia adaptativa IA (por defecto 5 picks)
        picks = await generateProPicks(5);
    } catch (error) {
        console.error('Error generating ProPicks:', error);
        picks = []; // En caso de error, mostrar lista vacía
    }

    if (picks.length === 0) {
        return (
            <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50 text-center">
                <h2 className="text-xl font-semibold mb-2 text-gray-200">ProPicks IA</h2>
                <p className="text-sm text-gray-400">
                    No hay picks disponibles ahora mismo. Puede ser un problema temporal
                    con los datos de mercado.
                </p>
                <Button asChild variant="outline" size="sm" className="gap-2 mt-4">
                    <Link href="/propicks">
                        Reintentar
                        <ArrowRight className="h-4 w-4" />
                    </Link>
                </Button>
            </Card>
        );
    }

    const currentMonth = new Date().toLocaleDateString('es-ES', { month: 'long', year: 'numeric' });

    return (
        <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <Sparkles className="h-6 w-6 text-teal-400" />
                    <div>
                        <h2 className="text-2xl font-bold text-gray-100">ProPicks IA</h2>
                        <p className="text-sm text-gray-400 mt-1">
                            Acciones seleccionadas por nuestra IA para {currentMonth}
                        </p>
                    </div>
                </div>
            </div>

            <p className="text-sm text-gray-300 mb-4">
                Encuentre acciones ganadoras seleccionadas por nuestra inteligencia artificial. 
                Cada pick ha sido evaluado usando análisis fundamental avanzado, múltiples métricas 
                y comparación con el sector (similar a Investing Pro).
            </p>

            {/* Mostrar desglose de categorías si hay picks */}
            {picks.length > 0 && (
                <div className="mb-6 p-4 bg-gray-900/50 rounded-lg border border-gray-700/50">
                    <h3 className="text-sm font-semibold text-gray-300 mb-3">Estrategia: Selección Adaptativa IA</h3>
                    <p className="text-xs text-gray-400 mb-3">
                        La IA analiza datos actuales del mercado y selecciona las mejores oportunidades,
                        comparando métricas con el promedio del sector. Pesos del score general:
                    </p>
                    <div className="grid grid-cols-3 md:grid-cols-6 gap-2 text-xs">
                        {(
                            [
                                ['Valor', SCORING_WEIGHTS.value],
                                ['Crecimiento', SCORING_WEIGHTS.growth],
                                ['Rentabilidad', SCORING_WEIGHTS.profitability],
                                ['Flujo Caja', SCORING_WEIGHTS.cashFlow],
                                ['Impulso', SCORING_WEIGHTS.momentum],
                                ['Deuda', SCORING_WEIGHTS.debtLiquidity],
                            ] as const
                        ).map(([label, weight]) => (
                            <div key={label}>
                                <div className="text-gray-500">{label}</div>
                                <div className="text-gray-300 font-medium">{Math.round(weight * 100)}%</div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                {picks.map((pick) => {
                    const getScoreColor = (score: number) => {
                        if (score >= 80) return 'text-green-400';
                        if (score >= 70) return 'text-teal-400';
                        return 'text-yellow-400';
                    };

                    const getGradeColor = (grade: string) => {
                        if (grade.startsWith('A')) return 'bg-green-500';
                        if (grade.startsWith('B')) return 'bg-teal-500';
                        return 'bg-yellow-500';
                    };

                    return (
                        <Link
                            key={pick.symbol}
                            href={`/research/${pick.symbol}`}
                            className="block p-4 bg-gray-900/50 hover:bg-gray-900 rounded-lg border border-gray-700/50 transition-all duration-200 group"
                        >
                            <div className="flex items-start justify-between mb-3">
                                <div className="flex-1">
                                    <div className="flex items-center gap-2 mb-1">
                                        <h3 className="text-lg font-semibold text-gray-100 group-hover:text-teal-400 transition-colors">
                                            {pick.symbol}
                                        </h3>
                                        <span className={`px-2 py-0.5 rounded text-xs font-bold text-white ${getGradeColor(pick.grade)}`}>
                                            {pick.grade}
                                        </span>
                                    </div>
                                    <p className="text-sm text-gray-400 line-clamp-1">{pick.company}</p>
                                    {pick.sector && (
                                        <p className="text-xs text-gray-500 mt-1">{pick.sector}</p>
                                    )}
                                </div>
                                <div className="text-right">
                                    <div className={`text-2xl font-bold ${getScoreColor(pick.score)}`}>
                                        {pick.score}
                                    </div>
                                    <div className="text-xs text-gray-500">Score</div>
                                    {pick.strategyScore && pick.strategyScore !== pick.score && (
                                        <div className="text-xs text-teal-400 mt-1">
                                            Estrategia: {pick.strategyScore}
                                        </div>
                                    )}
                                </div>
                            </div>
                            
                            {pick.currentPrice > 0 && (
                                <div className="text-sm text-gray-300 mb-3">
                                    <span className="font-medium">${pick.currentPrice.toFixed(2)}</span>
                                    <span className="ml-2 text-xs text-teal-400">
                                        Confianza {pick.confidenceLevel} ({pick.confidence}/100)
                                    </span>
                                </div>
                            )}

                            {pick.confidenceReasons.length > 0 && (
                                <div className="space-y-1">
                                    {pick.confidenceReasons.slice(0, 3).map((reason, index) => (
                                        <div key={index} className="flex items-center gap-2 text-xs text-gray-400" title={`Dato verificado: ${reason.metric} = ${reason.value}`}>
                                            <TrendingUp className="h-3 w-3 text-teal-400" />
                                            {reason.text}
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Mostrar comparación con sector si está disponible */}
                            {pick.vsSector && pick.sector && (
                                <div className="mt-3 pt-3 border-t border-gray-700/50">
                                    <div className="text-xs text-gray-500 mb-1">vs Sector</div>
                                    <div className="grid grid-cols-3 gap-2 text-xs">
                                        <div>
                                            <div className="text-gray-500">Valor</div>
                                            <div className={`font-medium ${pick.vsSector.value > 5 ? 'text-green-400' : pick.vsSector.value < -5 ? 'text-red-400' : 'text-gray-400'}`}>
                                                {pick.vsSector.value > 0 ? '+' : ''}{pick.vsSector.value.toFixed(0)}
                                            </div>
                                        </div>
                                        <div>
                                            <div className="text-gray-500">Crecimiento</div>
                                            <div className={`font-medium ${pick.vsSector.growth > 5 ? 'text-green-400' : pick.vsSector.growth < -5 ? 'text-red-400' : 'text-gray-400'}`}>
                                                {pick.vsSector.growth > 0 ? '+' : ''}{pick.vsSector.growth.toFixed(0)}
                                            </div>
                                        </div>
                                        <div>
                                            <div className="text-gray-500">Rentabilidad</div>
                                            <div className={`font-medium ${pick.vsSector.profitability > 5 ? 'text-green-400' : pick.vsSector.profitability < -5 ? 'text-red-400' : 'text-gray-400'}`}>
                                                {pick.vsSector.profitability > 0 ? '+' : ''}{pick.vsSector.profitability.toFixed(0)}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </Link>
                    );
                })}
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-gray-700">
                <p className="text-xs text-gray-500">
                    {picks.length} acciones seleccionadas por IA • Última actualización: {new Date().toLocaleDateString('es-ES')}
                </p>
                <Button asChild variant="outline" size="sm" className="gap-2">
                    <Link href="/propicks">
                        Ver todas
                        <ArrowRight className="h-4 w-4" />
                    </Link>
                </Button>
            </div>
        </Card>
    );
}


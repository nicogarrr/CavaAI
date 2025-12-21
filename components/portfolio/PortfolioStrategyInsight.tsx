'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Brain, AlertTriangle, CheckCircle, Lightbulb, ShieldCheck, Loader2, PlusCircle, ArrowUpCircle, TrendingUp } from 'lucide-react';
import { generatePortfolioStrategyAnalysis } from '@/lib/actions/ai.actions';
import { toast } from 'sonner';
import Link from 'next/link';

interface PortfolioStrategyInsightProps {
    portfolioSummary: any;
}

export function PortfolioStrategyInsight({ portfolioSummary }: PortfolioStrategyInsightProps) {
    const [analysis, setAnalysis] = useState<any>(null);
    const [loading, setLoading] = useState(false);

    async function handleAnalyze() {
        setLoading(true);
        try {
            const result = await generatePortfolioStrategyAnalysis(portfolioSummary);
            setAnalysis(result);
            if (result.alignmentScore > 80) {
                toast.success('¡Tu cartera está muy bien alineada con tu estrategia!');
            } else if (result.alignmentScore < 50) {
                toast.warning('Se detectaron desviaciones importantes de tu estrategia.');
            }
        } catch (error) {
            console.error(error);
            toast.error('Error al analizar la estrategia');
        } finally {
            setLoading(false);
        }
    }

    if (!analysis && !loading) {
        return (
            <Card className="bg-gradient-to-r from-slate-900 to-indigo-950 border-indigo-500/30 text-white">
                <CardContent className="flex items-center justify-between p-6">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-indigo-500/20 rounded-full">
                            <Brain className="h-8 w-8 text-indigo-400" />
                        </div>
                        <div>
                            <h3 className="text-lg font-semibold">Analista de Estrategia AI</h3>
                            <p className="text-slate-300 text-sm">
                                Audita tu cartera contra tus propias reglas de inversión (RAG).
                            </p>
                        </div>
                    </div>
                    <Button
                        onClick={handleAnalyze}
                        className="bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-500/20"
                    >
                        <ShieldCheck className="mr-2 h-4 w-4" />
                        Analizar Cumplimiento
                    </Button>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="border-indigo-500/30 bg-slate-950/50 backdrop-blur-sm">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Brain className="h-5 w-5 text-indigo-400" />
                        <CardTitle>Análisis de Estrategia Personal</CardTitle>
                    </div>
                    {analysis && (
                        <Badge variant={analysis.alignmentScore > 75 ? "default" : "destructive"} className="text-base px-3">
                            Score: {analysis.alignmentScore}/100
                        </Badge>
                    )}
                </div>
                <CardDescription>
                    Basado en tus documentos de conocimiento y reglas de inversión.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                {loading ? (
                    <div className="flex flex-col items-center justify-center py-8 space-y-4">
                        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
                        <p className="text-muted-foreground animate-pulse">Consultando tus reglas de inversión...</p>
                    </div>
                ) : (
                    <>
                        {/* Score Bar */}
                        <div className="space-y-2">
                            <div className="flex justify-between text-sm">
                                <span>Alineación con Estrategia</span>
                                <span className="font-medium">{analysis.alignmentScore}%</span>
                            </div>
                            <Progress value={analysis.alignmentScore} className="h-2" />
                        </div>

                        {/* Summary */}
                        <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-800">
                            <p className="text-sm text-slate-300 italic">"{analysis.summary}"</p>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {/* Warnings */}
                            <div className="space-y-3">
                                <h4 className="font-medium flex items-center gap-2 text-red-400">
                                    <AlertTriangle className="h-4 w-4" />
                                    Alertas
                                </h4>
                                {analysis.warnings.length === 0 ? (
                                    <p className="text-xs text-muted-foreground">Sin alertas graves.</p>
                                ) : (
                                    <ul className="space-y-2">
                                        {analysis.warnings.map((w: string, i: number) => (
                                            <li key={i} className="text-xs bg-red-500/10 text-red-300 p-2 rounded border border-red-500/20">
                                                {w}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>

                            {/* Strengths */}
                            <div className="space-y-3">
                                <h4 className="font-medium flex items-center gap-2 text-green-400">
                                    <CheckCircle className="h-4 w-4" />
                                    Aciertos
                                </h4>
                                <ul className="space-y-2">
                                    {analysis.strengths.map((s: string, i: number) => (
                                        <li key={i} className="text-xs bg-green-500/10 text-green-300 p-2 rounded border border-green-500/20">
                                            {s}
                                        </li>
                                    ))}
                                </ul>
                            </div>

                            {/* Opportunities */}
                            <div className="space-y-3">
                                <h4 className="font-medium flex items-center gap-2 text-amber-400">
                                    <Lightbulb className="h-4 w-4" />
                                    Sugerencias
                                </h4>
                                <ul className="space-y-2">
                                    {analysis.opportunities.map((o: string, i: number) => (
                                        <li key={i} className="text-xs bg-amber-500/10 text-amber-300 p-2 rounded border border-amber-500/20">
                                            {o}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        </div>

                        {/* Nueva sección: Acciones para añadir */}
                        {analysis.stocksToAdd && analysis.stocksToAdd.length > 0 && (
                            <div className="mt-6 p-4 bg-gradient-to-r from-cyan-950/30 to-blue-950/30 rounded-lg border border-cyan-500/20">
                                <h4 className="font-semibold flex items-center gap-2 text-cyan-400 mb-4">
                                    <PlusCircle className="h-5 w-5" />
                                    Acciones Recomendadas para Añadir
                                </h4>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                    {analysis.stocksToAdd.map((stock: { symbol: string; reason: string; potentialImpact: string }, i: number) => (
                                        <Link 
                                            key={i} 
                                            href={`/stocks/${stock.symbol}`}
                                            className="block p-3 bg-cyan-500/10 rounded-lg border border-cyan-500/30 hover:bg-cyan-500/20 transition-colors cursor-pointer"
                                        >
                                            <div className="flex items-center justify-between mb-2">
                                                <span className="font-bold text-cyan-300 text-lg">{stock.symbol}</span>
                                                <Badge variant="outline" className="text-cyan-400 border-cyan-500/50 text-xs">
                                                    Ver análisis →
                                                </Badge>
                                            </div>
                                            <p className="text-xs text-slate-300 mb-1">{stock.reason}</p>
                                            <p className="text-xs text-cyan-400/80 flex items-center gap-1">
                                                <TrendingUp className="h-3 w-3" />
                                                {stock.potentialImpact}
                                            </p>
                                        </Link>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Nueva sección: Cambios sugeridos con impacto en Score */}
                        {analysis.suggestedChanges && analysis.suggestedChanges.length > 0 && (
                            <div className="mt-6 p-4 bg-gradient-to-r from-purple-950/30 to-indigo-950/30 rounded-lg border border-purple-500/20">
                                <h4 className="font-semibold flex items-center gap-2 text-purple-400 mb-4">
                                    <ArrowUpCircle className="h-5 w-5" />
                                    Cambios para Mejorar tu Score
                                </h4>
                                <div className="space-y-3">
                                    {analysis.suggestedChanges.map((change: { action: string; symbol?: string; impact: string; newScoreEstimate: number }, i: number) => (
                                        <div 
                                            key={i} 
                                            className="p-3 bg-purple-500/10 rounded-lg border border-purple-500/30 flex items-start justify-between gap-4"
                                        >
                                            <div className="flex-1">
                                                <div className="flex items-center gap-2 mb-1">
                                                    {change.symbol && (
                                                        <Link href={`/stocks/${change.symbol}`} className="font-bold text-purple-300 hover:text-purple-200">
                                                            {change.symbol}
                                                        </Link>
                                                    )}
                                                    <span className="text-sm text-slate-200">{change.action}</span>
                                                </div>
                                                <p className="text-xs text-slate-400">{change.impact}</p>
                                            </div>
                                            <div className="text-right flex-shrink-0">
                                                <div className="text-xs text-slate-500 mb-1">Nuevo Score</div>
                                                <Badge 
                                                    variant={change.newScoreEstimate > analysis.alignmentScore ? "default" : "secondary"}
                                                    className={change.newScoreEstimate > analysis.alignmentScore ? "bg-green-600" : ""}
                                                >
                                                    {change.newScoreEstimate}/100
                                                    {change.newScoreEstimate > analysis.alignmentScore && (
                                                        <span className="ml-1 text-green-200">+{change.newScoreEstimate - analysis.alignmentScore}</span>
                                                    )}
                                                </Badge>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                                
                                {/* Score potencial máximo */}
                                {analysis.suggestedChanges.length > 0 && (
                                    <div className="mt-4 p-3 bg-gradient-to-r from-green-950/50 to-emerald-950/50 rounded-lg border border-green-500/30">
                                        <div className="flex items-center justify-between">
                                            <span className="text-sm text-green-300 font-medium">
                                                Si aplicas todos los cambios:
                                            </span>
                                            <div className="flex items-center gap-2">
                                                <span className="text-slate-400">{analysis.alignmentScore}</span>
                                                <span className="text-green-400">→</span>
                                                <Badge className="bg-green-600 text-lg px-3">
                                                    {Math.min(100, Math.max(...analysis.suggestedChanges.map((c: { newScoreEstimate: number }) => c.newScoreEstimate)))}/100
                                                </Badge>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Botón para re-analizar */}
                        <div className="mt-6 flex justify-center">
                            <Button
                                onClick={handleAnalyze}
                                variant="outline"
                                className="border-indigo-500/50 text-indigo-400 hover:bg-indigo-500/10"
                            >
                                <Brain className="mr-2 h-4 w-4" />
                                Re-analizar Cartera
                            </Button>
                        </div>
                    </>
                )}
            </CardContent>
        </Card>
    );
}

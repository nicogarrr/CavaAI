'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Brain, AlertTriangle, CheckCircle, Lightbulb, ShieldCheck, Loader2 } from 'lucide-react';
import { generatePortfolioStrategyAnalysis } from '@/lib/actions/ai.actions';
import { toast } from 'sonner';

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
                    </>
                )}
            </CardContent>
        </Card>
    );
}

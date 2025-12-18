'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, TrendingDown, TrendingUp, ShieldAlert, ArrowRight } from 'lucide-react';
import { generateRiskAnalysis } from '@/lib/actions/risk.actions';
import { toast } from 'sonner';

interface PortfolioRiskSimulatorProps {
    portfolioSummary: any;
}

export function PortfolioRiskSimulator({ portfolioSummary }: PortfolioRiskSimulatorProps) {
    const [scenario, setScenario] = useState<string>('recession_2025');
    const [analysis, setAnalysis] = useState<any>(null);
    const [loading, setLoading] = useState(false);

    async function handleSimulate() {
        if (!scenario) return;
        setLoading(true);
        try {
            const result = await generateRiskAnalysis(portfolioSummary, scenario);
            setAnalysis(result);
        } catch (error) {
            console.error(error);
            toast.error('Error al generar la simulación');
        } finally {
            setLoading(false);
        }
    }

    return (
        <Card className="border-red-500/20 bg-slate-950/50 backdrop-blur-sm">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <ShieldAlert className="h-5 w-5 text-red-400" />
                        <CardTitle>Simulador de Estrés (Stress Test)</CardTitle>
                    </div>
                </div>
                <CardDescription>
                    Simula cómo reaccionaría tu cartera ante eventos macroeconómicos extremos.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                <div className="flex gap-4">
                    <Select value={scenario} onValueChange={setScenario}>
                        <SelectTrigger className="w-[280px] bg-slate-900 border-slate-700">
                            <SelectValue placeholder="Selecciona un escenario" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="recession_2025">Recesión Global 2025</SelectItem>
                            <SelectItem value="inflation_high">Inflación Persistente (5%)</SelectItem>
                            <SelectItem value="tech_crash">Estallido Burbuja Tech</SelectItem>
                            <SelectItem value="soft_landing">Aterrizaje Suave (Optimista)</SelectItem>
                        </SelectContent>
                    </Select>
                    <Button
                        onClick={handleSimulate}
                        disabled={loading}
                        className="bg-red-900/50 hover:bg-red-900/70 text-red-100 border border-red-800"
                    >
                        {loading ? 'Simulando...' : 'Simular Impacto'}
                    </Button>
                </div>

                {analysis && (
                    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2">

                        {/* Main Stats */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800">
                                <p className="text-xs text-muted-foreground">Valor Actual</p>
                                <p className="text-xl font-mono text-white">${analysis.currentValue.toLocaleString()}</p>
                            </div>
                            <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 relative overflow-hidden">
                                <div className={`absolute inset-0 opacity-10 ${analysis.projectedChange >= 0 ? 'bg-green-500' : 'bg-red-500'}`} />
                                <p className="text-xs text-muted-foreground">Valor Proyectado</p>
                                <p className={`text-xl font-bold font-mono ${analysis.projectedChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    ${analysis.projectedValue.toLocaleString([], { maximumFractionDigits: 0 })}
                                </p>
                            </div>
                            <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center justify-between">
                                <div>
                                    <p className="text-xs text-muted-foreground">Impacto Estimado</p>
                                    <p className={`text-xl font-bold ${analysis.projectedChange >= 0 ? 'text-green-400' : 'text-red-500'}`}>
                                        {analysis.projectedChangePercent > 0 ? '+' : ''}{analysis.projectedChangePercent.toFixed(2)}%
                                    </p>
                                </div>
                                {analysis.projectedChange >= 0 ? <TrendingUp className="h-8 w-8 text-green-500/20" /> : <TrendingDown className="h-8 w-8 text-red-500/20" />}
                            </div>
                        </div>

                        {/* Analysis Details */}
                        <div className="p-4 bg-red-950/10 border border-red-900/20 rounded-lg">
                            <h4 className="text-sm font-semibold text-red-300 mb-2 flex items-center gap-2">
                                <AlertTriangle className="h-4 w-4" />
                                Análisis del Escenario: {analysis.scenario}
                            </h4>
                            <p className="text-sm text-slate-300 mb-4">{analysis.description}</p>

                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                                {analysis.worstHit && (
                                    <div className="bg-red-500/10 p-3 rounded border border-red-500/20">
                                        <p className="text-xs text-red-400 mb-1">Más Afectado</p>
                                        <div className="flex justify-between items-center">
                                            <span className="font-bold text-red-200">{analysis.worstHit.symbol}</span>
                                            <span className="font-mono text-red-400">{analysis.worstHit.changePercent.toFixed(2)}%</span>
                                        </div>
                                    </div>
                                )}
                                {analysis.bestPerformer && (
                                    <div className="bg-green-500/10 p-3 rounded border border-green-500/20">
                                        <p className="text-xs text-green-400 mb-1">Mejor Comportamiento</p>
                                        <div className="flex justify-between items-center">
                                            <span className="font-bold text-green-200">{analysis.bestPerformer.symbol}</span>
                                            <span className="font-mono text-green-400">{analysis.bestPerformer.changePercent > 0 ? '+' : ''}{analysis.bestPerformer.changePercent.toFixed(2)}%</span>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

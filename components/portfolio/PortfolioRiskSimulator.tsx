'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ShieldAlert, TrendingDown, TrendingUp, AlertTriangle, RefreshCw } from 'lucide-react';
import { generateRiskAnalysis, type MonteCarloResult } from '@/lib/actions/risk.actions';
import { toast } from 'sonner';

interface PortfolioRiskSimulatorProps {
    userId: string;
}

function fmt(n: number | null | undefined, decimals = 1): string {
    if (n == null) return '—';
    return `${n >= 0 ? '+' : ''}${(n * 100).toFixed(decimals)}%`;
}

function fmtProb(n: number | null | undefined): string {
    if (n == null) return '—';
    return `${(n * 100).toFixed(1)}%`;
}

export function PortfolioRiskSimulator({ userId }: PortfolioRiskSimulatorProps) {
    const [result, setResult] = useState<MonteCarloResult | null>(null);
    const [loading, setLoading] = useState(false);

    async function handleSimulate() {
        setLoading(true);
        try {
            const data = await generateRiskAnalysis(userId, 252, 500);
            if ('error' in data) {
                toast.error(data.error);
                return;
            }
            setResult(data);
        } catch (error) {
            console.error(error);
            toast.error('Error al ejecutar la simulación Monte Carlo');
        } finally {
            setLoading(false);
        }
    }

    const models = result ? Object.values(result.models) : [];

    return (
        <Card className="border-red-500/20 bg-slate-950/50 backdrop-blur-sm">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <ShieldAlert className="h-5 w-5 text-red-400" />
                        <CardTitle>Simulación Monte Carlo</CardTitle>
                    </div>
                </div>
                <CardDescription>
                    Distribución probabilística de retornos a 1 año vía modelos estocásticos (GBM, Bootstrap, Block Bootstrap, GARCH).
                </CardDescription>
            </CardHeader>

            <CardContent className="space-y-6">
                <Button
                    onClick={handleSimulate}
                    disabled={loading}
                    className="bg-red-900/50 hover:bg-red-900/70 text-red-100 border border-red-800"
                >
                    {loading ? (
                        <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Simulando ({500} paths)…</>
                    ) : (
                        'Ejecutar Simulación'
                    )}
                </Button>

                {result && (
                    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2">

                        {/* Cross-model summary */}
                        <div className="grid grid-cols-3 gap-4">
                            <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800">
                                <p className="text-xs text-muted-foreground">Mediana entre modelos</p>
                                <p className={`text-xl font-mono font-bold ${(result.summary.cross_model_median_return ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {fmt(result.summary.cross_model_median_return)}
                                </p>
                            </div>
                            <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800">
                                <p className="text-xs text-muted-foreground">Envelope conservador</p>
                                <p className={`text-xl font-mono font-bold ${(result.summary.conservative_envelope ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {fmt(result.summary.conservative_envelope)}
                                </p>
                            </div>
                            <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800">
                                <p className="text-xs text-muted-foreground">Modelos ejecutados</p>
                                <p className="text-xl font-mono text-white">{result.summary.models_run}</p>
                            </div>
                        </div>

                        {/* Per-model breakdown */}
                        <div className="space-y-2">
                            <p className="text-xs text-muted-foreground uppercase tracking-wider">Distribución por modelo (horizonte {result.horizon_days}d)</p>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {models.map(m => (
                                    <div key={m.name} className="p-3 rounded bg-slate-900/60 border border-slate-800">
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="text-sm font-semibold text-white">{m.label}</span>
                                            <span className="text-xs text-muted-foreground">{m.category}</span>
                                        </div>
                                        <div className="grid grid-cols-3 gap-1 text-xs font-mono">
                                            <div>
                                                <p className="text-red-400">P5</p>
                                                <p>{fmt(m.percentile_5)}</p>
                                            </div>
                                            <div className="text-center">
                                                <p className="text-slate-400">Mediana</p>
                                                <p className={`font-bold ${(m.median ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>{fmt(m.median)}</p>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-green-400">P95</p>
                                                <p>{fmt(m.percentile_95)}</p>
                                            </div>
                                        </div>
                                        <div className="flex justify-between mt-2 text-xs text-muted-foreground">
                                            <span>Bust (&lt;−50%): <span className="text-red-400">{fmtProb(m.bust_probability)}</span></span>
                                            <span>Goal (&gt;+50%): <span className="text-green-400">{fmtProb(m.goal_probability)}</span></span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="flex items-start gap-2 p-3 rounded bg-amber-950/20 border border-amber-900/30 text-xs text-amber-300">
                            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                            <span>
                                Los modelos se calibran sobre retornos históricos de la cartera actual.
                                Resultados son distribuciones de probabilidad, no predicciones.
                                Horizonte: {result.horizon_days} días · {result.simulations.toLocaleString()} simulaciones por modelo.
                            </span>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

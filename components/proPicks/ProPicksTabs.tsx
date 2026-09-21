'use client';

import { useEffect, useState } from 'react';
import { BarChart3, Loader2, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import BacktestResults from './BacktestResults';
import EnhancedProPicksContent from './EnhancedProPicksContent';
import StrategySelector from './StrategySelector';
import { runStrategyBacktest, type StrategyBacktestOutput } from '@/lib/actions/propicks-backtest.actions';
import type { ProPick } from '@/lib/actions/proPicks.actions';

interface ProPicksTabsProps {
    strategies: Array<{ id: string; name: string; description: string }>;
    initialPicks: ProPick[];
    generatedAt?: string;
}

export default function ProPicksTabs({ strategies, initialPicks, generatedAt }: ProPicksTabsProps) {
    const [currentStrategy, setCurrentStrategy] = useState<string>(strategies[0]?.id ?? 'adaptive');
    const [backtest, setBacktest] = useState<StrategyBacktestOutput | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const runBacktest = async (strategyId: string) => {
        setLoading(true);
        setError(null);
        try {
            const output = await runStrategyBacktest(strategyId);
            if ('error' in output) {
                setError(output.error);
                setBacktest(null);
            } else {
                setBacktest(output);
            }
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : String(caught));
            setBacktest(null);
        } finally {
            setLoading(false);
        }
    };

    // Backtest inicial con la primera estrategia disponible (típicamente 'adaptive')
    useEffect(() => {
        void runBacktest(strategies[0]?.id ?? 'adaptive');
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleStrategyChange = (strategyId: string) => {
        setCurrentStrategy(strategyId);
        void runBacktest(strategyId);
    };

    return (
        <Tabs defaultValue="picks" className="mt-6">
            <TabsList className="inline-flex border border-gray-700 bg-gray-800 text-gray-400">
                <TabsTrigger value="picks" className="data-[state=active]:bg-gray-700 data-[state=active]:text-teal-300">
                    Picks IA
                </TabsTrigger>
                <TabsTrigger value="backtest" className="data-[state=active]:bg-gray-700 data-[state=active]:text-teal-300">
                    Backtesting
                </TabsTrigger>
            </TabsList>

            <TabsContent value="picks" className="mt-6">
                <EnhancedProPicksContent initialPicks={initialPicks} generatedAt={generatedAt} />
            </TabsContent>

            <TabsContent value="backtest" className="mt-6 space-y-4">
                <Card className="flex flex-col gap-4 rounded-lg border border-gray-700 bg-gray-800/50 p-4 md:flex-row md:items-center md:justify-between">
                    <StrategySelector
                        strategies={strategies}
                        currentStrategy={currentStrategy}
                        onStrategyChange={handleStrategyChange}
                    />
                    <Button
                        onClick={() => runBacktest(currentStrategy)}
                        disabled={loading}
                        className="gap-2 bg-teal-600 hover:bg-teal-700"
                    >
                        {loading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Play className="h-4 w-4" />
                        )}
                        {loading ? 'Calculando...' : 'Ejecutar Backtest'}
                    </Button>
                </Card>

                {error && (
                    <Card className="rounded-lg border border-red-700 bg-red-900/20 p-6 text-center">
                        <p className="text-red-400">{error}</p>
                        <p className="text-sm text-gray-400 mt-2">
                            No se pudo calcular el backtest. Comprueba tu conexión e inténtalo de nuevo.
                        </p>
                        <Button
                            onClick={() => runBacktest(currentStrategy)}
                            disabled={loading}
                            className="mt-4 gap-2 bg-teal-600 hover:bg-teal-700"
                        >
                            {loading ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <Play className="h-4 w-4" />
                            )}
                            Reintentar
                        </Button>
                    </Card>
                )}

                {loading && !backtest && (
                    <Card className="flex items-center justify-center gap-3 rounded-lg border border-gray-700 bg-gray-800/50 p-10 text-gray-400">
                        <Loader2 className="h-5 w-5 animate-spin text-teal-400" />
                        <span>Calculando backtest con datos históricos... puede tardar unos segundos.</span>
                    </Card>
                )}

                {backtest && !loading && <BacktestResults result={backtest.result} />}

                {!loading && !error && !backtest && (
                    <Card className="flex flex-col items-center gap-3 rounded-lg border border-gray-700 bg-gray-800/50 p-10 text-gray-500">
                        <BarChart3 className="h-10 w-10 text-gray-600" />
                        <p className="text-sm">Selecciona una estrategia y pulsa «Ejecutar Backtest» para ver el desempeño simulado.</p>
                    </Card>
                )}
            </TabsContent>
        </Tabs>
    );
}
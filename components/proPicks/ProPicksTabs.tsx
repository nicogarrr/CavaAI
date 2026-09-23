'use client';

import { useEffect, useState } from 'react';
import { BarChart3, Loader2, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import BacktestResults from './BacktestResults';
import EnhancedProPicksContent from './EnhancedProPicksContent';
import MonthlyRebalanceView from './MonthlyRebalanceView';
import StrategyFactsheet from './StrategyFactsheet';
import StrategySelector from './StrategySelector';
import { STRATEGY_CATALOG, mergeStrategies } from './monthlyRebalance';
import { runStrategyBacktest, type StrategyBacktestOutput } from '@/lib/actions/propicks-backtest.actions';
import type { ProPick } from '@/lib/actions/proPicks.actions';

interface ProPicksTabsProps {
    strategies: Array<{ id: string; name: string; description: string }>;
    initialPicks: ProPick[];
    generatedAt?: string;
}

export default function ProPicksTabs({ strategies, initialPicks, generatedAt }: ProPicksTabsProps) {
    const merged = mergeStrategies(strategies);
    const [currentStrategy, setCurrentStrategy] = useState<string>(merged[0]?.id ?? 'adaptive');
    const [backtests, setBacktests] = useState<Record<string, StrategyBacktestOutput | null>>({});
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const availableIds = new Set(strategies.map((s) => s.id));
    const currentMerged = merged.find((s) => s.id === currentStrategy) ?? merged[0];
    const currentAvailable = currentMerged ? availableIds.has(currentMerged.id) : false;

    const runBacktest = async (strategyId: string) => {
        // Sin llamar al servidor cuando la estrategia aún no tiene datos:
        // runStrategyBacktest caería al fallback 'adaptive' y mezclaría números.
        if (!availableIds.has(strategyId)) {
            setBacktests((prev) => ({ ...prev, [strategyId]: null }));
            setError(null);
            return;
        }
        setLoading(true);
        setError(null);
        try {
            const output = await runStrategyBacktest(strategyId);
            if ('error' in output) {
                setError(output.error);
                setBacktests((prev) => ({ ...prev, [strategyId]: null }));
            } else {
                setBacktests((prev) => ({ ...prev, [strategyId]: output }));
            }
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : String(caught));
            setBacktests((prev) => ({ ...prev, [strategyId]: null }));
        } finally {
            setLoading(false);
        }
    };

    // Backtest inicial con la primera estrategia disponible
    useEffect(() => {
        const firstAvailable = merged.find((s) => availableIds.has(s.id))?.id ?? merged[0]?.id;
        if (firstAvailable) void runBacktest(firstAvailable);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleStrategyChange = (strategyId: string) => {
        setCurrentStrategy(strategyId);
        void runBacktest(strategyId);
    };

    const currentBacktest = backtests[currentStrategy] ?? null;

    return (
        <Tabs defaultValue="picks" className="mt-6 w-full min-w-0">
            <TabsList className="grid w-full grid-cols-4 border border-gray-700 bg-gray-800 text-gray-400 sm:inline-flex sm:w-auto">
                <TabsTrigger value="picks" className="min-h-[44px] data-[state=active]:bg-gray-700 data-[state=active]:text-teal-300">
                    Picks IA
                </TabsTrigger>
                <TabsTrigger value="estrategias" className="min-h-[44px] data-[state=active]:bg-gray-700 data-[state=active]:text-teal-300">
                    Estrategias
                </TabsTrigger>
                <TabsTrigger value="rebalanceo" className="min-h-[44px] data-[state=active]:bg-gray-700 data-[state=active]:text-teal-300">
                    Rebalanceo
                </TabsTrigger>
                <TabsTrigger value="backtest" className="min-h-[44px] data-[state=active]:bg-gray-700 data-[state=active]:text-teal-300">
                    Backtesting
                </TabsTrigger>
            </TabsList>

            <TabsContent value="picks" className="mt-6">
                <EnhancedProPicksContent initialPicks={initialPicks} generatedAt={generatedAt} />
            </TabsContent>

            <TabsContent value="estrategias" className="mt-6 space-y-4">
                <Card className="flex min-w-0 flex-col gap-4 rounded-lg border border-gray-700 bg-gray-800/50 p-4 md:flex-row md:items-center md:justify-between">
                    <StrategySelector
                        strategies={strategies}
                        catalog={STRATEGY_CATALOG}
                        currentStrategy={currentStrategy}
                        onStrategyChange={handleStrategyChange}
                    />
                    <Button
                        onClick={() => runBacktest(currentStrategy)}
                        disabled={loading || !currentAvailable}
                        className="h-11 w-full gap-2 bg-teal-600 hover:bg-teal-700 md:w-auto"
                    >
                        {loading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Play className="h-4 w-4" />
                        )}
                        {loading ? 'Calculando...' : 'Ejecutar Backtest'}
                    </Button>
                </Card>

                {currentMerged && (
                    <StrategyFactsheet
                        strategyId={currentMerged.id}
                        name={currentMerged.name}
                        description={currentMerged.description}
                        available={currentAvailable}
                        backtest={currentBacktest}
                        loading={loading}
                        error={error}
                    />
                )}
            </TabsContent>

            <TabsContent value="rebalanceo" className="mt-6">
                <MonthlyRebalanceView
                    currentPicks={initialPicks}
                    strategyId={currentStrategy}
                    strategyName={currentMerged?.name}
                />
            </TabsContent>

            <TabsContent value="backtest" className="mt-6 space-y-4">
                <Card className="flex min-w-0 flex-col gap-4 rounded-lg border border-gray-700 bg-gray-800/50 p-4 md:flex-row md:items-center md:justify-between">
                    <StrategySelector
                        strategies={strategies}
                        catalog={STRATEGY_CATALOG}
                        currentStrategy={currentStrategy}
                        onStrategyChange={handleStrategyChange}
                    />
                    <Button
                        onClick={() => runBacktest(currentStrategy)}
                        disabled={loading || !currentAvailable}
                        className="h-11 w-full gap-2 bg-teal-600 hover:bg-teal-700 md:w-auto"
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
                            className="mt-4 h-11 w-full gap-2 bg-teal-600 hover:bg-teal-700 sm:w-auto"
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

                {loading && !currentBacktest && (
                    <Card className="flex items-center justify-center gap-3 rounded-lg border border-gray-700 bg-gray-800/50 p-10 text-gray-400">
                        <Loader2 className="h-5 w-5 animate-spin text-teal-400" />
                        <span>Calculando backtest con datos históricos... puede tardar unos segundos.</span>
                    </Card>
                )}

                {currentBacktest && !loading && <BacktestResults result={currentBacktest.result} />}

                {!loading && !error && !currentBacktest && (
                    <Card className="flex flex-col items-center gap-3 rounded-lg border border-gray-700 bg-gray-800/50 p-10 text-gray-500">
                        <BarChart3 className="h-10 w-10 text-gray-600" />
                        <p className="text-sm">Selecciona una estrategia y pulsa «Ejecutar Backtest» para ver el desempeño simulado.</p>
                    </Card>
                )}
            </TabsContent>
        </Tabs>
    );
}

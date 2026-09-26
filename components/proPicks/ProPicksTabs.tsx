'use client';

import { useEffect, useState } from 'react';
import { BarChart3, Loader2, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import EnhancedProPicksContent from './EnhancedProPicksContent';
import MonthlyRebalanceView from './MonthlyRebalanceView';
import StrategyFactsheet from './StrategyFactsheet';
import StrategySelector from './StrategySelector';
import WalkForwardResults from './WalkForwardResults';
import { STRATEGY_CATALOG, mergeStrategies } from './monthlyRebalance';
import { runWalkForwardBacktest, type WalkForwardBacktestResult } from '@/lib/actions/propicks-backtest.actions';
import type { ProPick } from '@/lib/actions/proPicks.actions';

interface ProPicksTabsProps {
    strategies: Array<{ id: string; name: string; description: string }>;
    initialPicks: ProPick[];
    generatedAt?: string;
}

export default function ProPicksTabs({ strategies, initialPicks, generatedAt }: ProPicksTabsProps) {
    const merged = mergeStrategies(strategies);
    const [currentStrategy, setCurrentStrategy] = useState<string>(merged[0]?.id ?? 'adaptive');
    const [walkForward, setWalkForward] = useState<WalkForwardBacktestResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const availableIds = new Set(strategies.map((s) => s.id));
    const currentMerged = merged.find((s) => s.id === currentStrategy) ?? merged[0];
    const currentAvailable = currentMerged ? availableIds.has(currentMerged.id) : false;

    const runBacktest = async () => {
        // Motor walk-forward point-in-time: agnóstico de estrategia (momentum
        // 12-1M sobre universo líquido, costes de 15pb por pata, benchmark SPY).
        // El backtest por estrategia se publicará cuando haya fundamentales
        // point-in-time; hasta entonces NO se simula nada con datos de hoy.
        setLoading(true);
        setError(null);
        try {
            const output = await runWalkForwardBacktest();
            if ('error' in output) {
                setError(output.error);
                setWalkForward(null);
            } else {
                setWalkForward(output);
            }
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : String(caught));
            setWalkForward(null);
        } finally {
            setLoading(false);
        }
    };

    // Backtest walk-forward inicial al abrir la página
    useEffect(() => {
        void runBacktest();
    }, []);

    const handleStrategyChange = (strategyId: string) => {
        setCurrentStrategy(strategyId);
    };

    return (
        <Tabs defaultValue="picks" className="mt-6 w-full min-w-0">
            {/* `overflow-x-auto` en movil: con teclado no hay barra de scroll, asi que
                el list scrollea necesita ser alcanzable (WCAG 2.1.1). No se le pone
                `role="region"` porque sobrescribiria el `tablist` de Radix y la
                navegacion con flechas; `tabIndex` + nombre accesible bastan. */}
            <TabsList
                tabIndex={0}
                aria-label="Secciones de Pro Picks"
                className="flex h-auto w-max min-w-full snap-x gap-1 overflow-x-auto border border-gray-700 bg-gray-800 pb-2 text-gray-400 sm:inline-flex sm:h-9 sm:w-auto sm:overflow-visible sm:pb-[3px]"
            >
                <TabsTrigger value="picks" className="min-h-[44px] min-w-fit flex-none snap-start whitespace-nowrap data-[state=active]:bg-gray-700 data-[state=active]:text-teal-300">
                    Picks IA
                </TabsTrigger>
                <TabsTrigger value="estrategias" className="min-h-[44px] min-w-fit flex-none snap-start whitespace-nowrap data-[state=active]:bg-gray-700 data-[state=active]:text-teal-300">
                    Estrategias
                </TabsTrigger>
                <TabsTrigger value="rebalanceo" className="min-h-[44px] min-w-fit flex-none snap-start whitespace-nowrap data-[state=active]:bg-gray-700 data-[state=active]:text-teal-300">
                    Rebalanceo
                </TabsTrigger>
                <TabsTrigger value="backtest" className="min-h-[44px] min-w-fit flex-none snap-start whitespace-nowrap data-[state=active]:bg-gray-700 data-[state=active]:text-teal-300">
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
                </Card>

                {currentMerged && (
                    <StrategyFactsheet
                        strategyId={currentMerged.id}
                        name={currentMerged.name}
                        description={currentMerged.description}
                        available={currentAvailable}
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
                    <p className="max-w-xl text-sm leading-6 text-gray-400">
                        Baseline walk-forward point-in-time (momentum 12-1M,
                        universo líquido de 30 valores, costes 15 pb por pata,
                        SPY como benchmark). No valida los Picks IA de arriba:
                        valida que el motor no mira el futuro. El backtest por
                        estrategia con fundamentales point-in-time llegará
                        cuando haya TTM persistido.
                    </p>
                    <Button
                        onClick={() => runBacktest()}
                        disabled={loading}
                        aria-busy={loading}
                        className="h-11 w-full gap-2 bg-teal-600 hover:bg-teal-700 md:w-auto"
                    >
                        {loading ? (
                            <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
                        ) : (
                            <Play aria-hidden="true" className="h-4 w-4" />
                        )}
                        {loading ? 'Calculando...' : 'Ejecutar backtest'}
                    </Button>
                </Card>

                {error && (
                    <Card className="rounded-lg border border-red-700 bg-red-900/20 p-6 text-center">
                        <p className="text-red-400">{error}</p>
                        <p className="text-sm text-gray-400 mt-2">
                            No se pudo calcular el backtest. Comprueba tu conexión e inténtalo de nuevo.
                        </p>
                        <Button
                            onClick={() => runBacktest()}
                            disabled={loading}
                            aria-busy={loading}
                            className="mt-4 h-11 w-full gap-2 bg-teal-600 hover:bg-teal-700 sm:w-auto"
                        >
                            {loading ? (
                                <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
                            ) : (
                                <Play aria-hidden="true" className="h-4 w-4" />
                            )}
                            Reintentar
                        </Button>
                    </Card>
                )}

                {loading && !walkForward && (
                    <Card aria-busy="true" className="flex items-center justify-center gap-3 rounded-lg border border-gray-700 bg-gray-800/50 p-10 text-gray-400">
                        <Loader2 aria-hidden="true" className="h-5 w-5 animate-spin text-teal-400" />
                        <span>Calculando backtest walk-forward con datos históricos... puede tardar unos segundos.</span>
                    </Card>
                )}

                {walkForward && !loading && <WalkForwardResults result={walkForward} />}

                {!loading && !error && !walkForward && (
                    <Card className="flex flex-col items-center gap-3 rounded-lg border border-gray-700 bg-gray-800/50 p-10 text-gray-500">
                        <BarChart3 aria-hidden="true" className="h-10 w-10 text-gray-500" />
                        <p className="text-sm">Pulsa «Ejecutar backtest» para lanzar la simulación walk-forward point-in-time.</p>
                    </Card>
                )}
            </TabsContent>
        </Tabs>
    );
}

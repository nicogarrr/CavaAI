'use client';

import { formatMoney } from '@/lib/format';
import { useState, useMemo } from 'react';
import Link from 'next/link';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import dynamic from 'next/dynamic';
import PortfolioSummary from '@/components/portfolio/PortfolioSummary';
import PortfolioHoldings from '@/components/portfolio/PortfolioHoldings';
import PortfolioTransactions from '@/components/portfolio/PortfolioTransactions';
import PortfolioAllocation from '@/components/portfolio/PortfolioAllocation';
const PortfolioNavChart = dynamic(() => import('./PortfolioNavChart'), {
    ssr: false,
    loading: () => (
        <div className="h-full w-full animate-pulse rounded-lg border border-gray-800 bg-gray-900/40" aria-label="Cargando gráfico" role="status" />
    ),
});
import PortfolioScores from '@/components/portfolio/PortfolioScores';
import PortfolioTearsheet from '@/components/portfolio/PortfolioTearsheet';
import { PortfolioRiskSimulator } from '@/components/portfolio/PortfolioRiskSimulator';
import AddTransactionButton from '@/components/portfolio/AddTransactionButton';
import RefreshPortfolioButton from '@/components/portfolio/RefreshPortfolioButton';
import ImportIBKRButton from '@/components/portfolio/ImportIBKRButton';
import { PortfolioChat } from '@/components/portfolio/PortfolioChat';
import { Wallet, LayoutDashboard, Briefcase, TrendingUp, TrendingDown, History, Brain, ShieldAlert, Activity } from 'lucide-react';
import type { PortfolioPerformanceHistory, PortfolioSummary as PortfolioSummaryType, PortfolioTearsheet as PortfolioTearsheetType } from '@/lib/actions/portfolio.actions';

type Transaction = {
    _id: string;
    symbol: string;
    type: 'buy' | 'sell';
    quantity: number;
    price: number;
    date: string;
    notes?: string;
};

type Props = {
    summary: PortfolioSummaryType;
    transactions: Transaction[];
    scores: { quality: number; growth: number; value: number; dividend: number; cagr3y: number; history?: PortfolioPerformanceHistory };
    tearsheet: PortfolioTearsheetType | null;
    userId: string;
};

export default function PortfolioTabs({ summary, transactions, scores, tearsheet, userId }: Props) {
    const [activeTab, setActiveTab] = useState('resumen');
    const [chartPeriod, setChartPeriod] = useState('1M');

    const chartData = useMemo(() => {
        if (scores.history?.dates?.length && scores.history.nav?.length) {
            const latestDate = new Date(`${scores.history.dates.at(-1)}T00:00:00`);
            const yearStart = new Date(latestDate.getFullYear(), 0, 1);
            const ytdPoints = Math.max(1, scores.history.dates.filter((date) => new Date(`${date}T00:00:00`) >= yearStart).length);
            const rows = scores.history.dates.map((date, index) => ({
                date: new Date(`${date}T00:00:00`).toLocaleDateString('es-ES', { day: '2-digit', month: 'short' }),
                value: scores.history?.nav[index] ?? 0,
            }));
            const maxPoints: Record<string, number> = {
                '1S': 7,
                '1M': 30,
                '3M': 90,
                '6M': 180,
                'YTD': ytdPoints,
                '1A': 365,
                'Todo': rows.length,
            };
            return rows.slice(-Math.min(rows.length, maxPoints[chartPeriod] ?? 30));
        }

        return [];
    }, [chartPeriod, scores.history]);
    return (
        <div className="flex min-h-screen flex-col p-4 sm:p-4 lg:p-6 max-w-[1600px] mx-auto w-full overflow-x-clip">
                {/* Header */}
                <div className="flex flex-col gap-4 mb-6 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-3">
                        <div className="h-10 w-10 shrink-0 rounded-xl bg-gradient-to-br from-teal-500 to-blue-600 flex items-center justify-center">
                            <Wallet className="h-5 w-5 text-white" />
                        </div>
                        <div className="min-w-0">
                            <h1 className="text-xl font-bold text-gray-100 sm:text-2xl">Mi Cartera</h1>
                            <p className="text-sm text-gray-500">Seguimiento de tus inversiones</p>
                        </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center sm:justify-end">
                        <Link className="inline-flex min-h-[44px] col-span-2 items-center justify-center gap-2 rounded-md border border-gray-700 px-3 py-2.5 text-sm text-gray-300 transition hover:border-teal-700 hover:text-teal-300 sm:col-span-1 sm:min-h-0 sm:h-9 sm:w-auto" href="/portfolio/intelligence">
                            <Activity className="h-4 w-4" /> Intelligence
                        </Link>
                        <RefreshPortfolioButton userId={userId} />
                                            <ImportIBKRButton userId={userId} />
                                            <AddTransactionButton userId={userId} />
                    </div>
                </div>

                {/* Tabs Navigation */}
                <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                <div className="-mx-4 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
                    <TabsList className="bg-[#0a0a0a] border border-gray-800 p-1 rounded-xl mb-6 flex w-max max-w-none gap-1">
                    <TabsTrigger
                        value="resumen"
                        className="data-[state=active]:bg-gray-800 data-[state=active]:text-white rounded-lg px-4 py-2.5 text-sm text-gray-400 flex items-center gap-2 min-h-[44px] sm:min-h-0 sm:py-2 whitespace-nowrap"
                    >
                        <LayoutDashboard className="h-4 w-4" />
                        Resumen
                    </TabsTrigger>
                    <TabsTrigger
                        value="posiciones"
                        className="data-[state=active]:bg-gray-800 data-[state=active]:text-white rounded-lg px-4 py-2.5 text-sm text-gray-400 flex items-center gap-2 min-h-[44px] sm:min-h-0 sm:py-2 whitespace-nowrap"
                    >
                        <Briefcase className="h-4 w-4" />
                        Posiciones
                    </TabsTrigger>
                    <TabsTrigger
                        value="movimientos"
                        className="data-[state=active]:bg-gray-800 data-[state=active]:text-white rounded-lg px-4 py-2.5 text-sm text-gray-400 flex items-center gap-2 min-h-[44px] sm:min-h-0 sm:py-2 whitespace-nowrap"
                    >
                        <History className="h-4 w-4" />
                        Movimientos
                    </TabsTrigger>
                    <TabsTrigger
                        value="estrategia"
                        className="data-[state=active]:bg-gray-800 data-[state=active]:text-white rounded-lg px-4 py-2.5 text-sm text-gray-400 flex items-center gap-2 min-h-[44px] sm:min-h-0 sm:py-2 whitespace-nowrap"
                    >
                        <Brain className="h-4 w-4" />
                        Factores
                    </TabsTrigger>
                    <TabsTrigger
                        value="riesgo"
                        className="data-[state=active]:bg-gray-800 data-[state=active]:text-white rounded-lg px-4 py-2.5 text-sm text-gray-400 flex items-center gap-2 min-h-[44px] sm:min-h-0 sm:py-2 whitespace-nowrap"
                    >
                        <ShieldAlert className="h-4 w-4" />
                        Riesgo
                    </TabsTrigger>
                </TabsList>
                </div>

                {/* Tab: Resumen */}
                <TabsContent value="resumen" className="mt-0">
                    {/* Métricas en fila */}
                    <div className="mb-6">
                        <PortfolioSummary summary={summary} />
                    </div>

                    {/* Grid: gráfico de rendimiento + distribución */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* Panel Izquierdo: Gráfico de Rendimiento */}
                        <div className="bg-[#111111] border border-gray-800 rounded-2xl p-4 sm:p-6">
                            <div className="flex flex-col gap-3 mb-4 sm:flex-row sm:items-center sm:justify-between">
                                <h3 className="text-gray-400 text-sm font-medium">Rendimiento Total</h3>
                                <div className="flex flex-wrap gap-1">
                                    {['1S', '1M', '3M', '6M', 'YTD', '1A', 'Todo'].map((period) => (
                                        <button
                                            key={period}
                                            onClick={() => setChartPeriod(period)}
                                            className={`min-h-[44px] px-3 py-2 text-xs rounded transition-colors sm:min-h-0 sm:px-2 sm:py-1 ${chartPeriod === period
                                                    ? 'bg-gray-700 text-white'
                                                    : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'
                                                }`}
                                        >
                                            {period}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="mb-4">
                                <p className="text-3xl font-bold text-white">
                                    {formatMoney(summary.totalValue)}
                                </p>
                                <p className={`text-sm flex items-center gap-1 ${summary.totalGain >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {summary.totalGain >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                                    {summary.totalGain >= 0 ? '+' : ''}{summary.totalGainPercent.toFixed(2)}%
                                    <span className="text-gray-500">
                                        ({summary.totalGain >= 0 ? '+' : ''}{formatMoney(summary.totalGain)})
                                    </span>
                                </p>
                            </div>

                            {/* Gráfico de área */}
                            <div className="h-[200px]">
                                {chartData.length === 0 ? (
                                    <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-gray-800 text-sm text-gray-500">
                                        El historial aparecerá cuando existan snapshots reales de la cartera.
                                    </div>
                                ) : (
                                <PortfolioNavChart data={chartData} positive={summary.totalGain >= 0} />
                                )}
                            </div>
                        </div>

                        {/* Panel Derecho: Pie Chart Completo */}
                        <PortfolioAllocation
                            holdings={summary.holdings}
                            totalValue={summary.totalValue}
                        />
                    </div>

                    {/* Tearsheet: Sharpe, drawdown, win rate */}
                    <div className="mt-6">
                        <PortfolioTearsheet tearsheet={tearsheet} />
                    </div>
                </TabsContent>

                {/* Tab: Posiciones */}
                <TabsContent value="posiciones" className="mt-0">
                    <PortfolioHoldings holdings={summary.holdings} userId={userId} />
                </TabsContent>

                {/* Tab: Movimientos */}
                <TabsContent value="movimientos" className="mt-0">
                    <div className="max-w-4xl">
                        <PortfolioTransactions transactions={transactions} userId={userId} />
                    </div>
                </TabsContent>

                {/* Tab: factores calculados */}
                <TabsContent value="estrategia" className="mt-0">
                    <PortfolioScores scores={scores} />
                </TabsContent>

                {/* Tab: Riesgo Monte Carlo */}
                <TabsContent value="riesgo" className="mt-0">
                    <PortfolioRiskSimulator userId={userId} />
                </TabsContent>
            </Tabs>

            <PortfolioChat userId={userId} />
        </div>
    );
}

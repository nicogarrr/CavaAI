'use client';

import { useState, useMemo } from 'react';
import Link from 'next/link';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts';
import PortfolioSummary from '@/components/portfolio/PortfolioSummary';
import PortfolioHoldings from '@/components/portfolio/PortfolioHoldings';
import PortfolioTransactions from '@/components/portfolio/PortfolioTransactions';
import PortfolioAllocation from '@/components/portfolio/PortfolioAllocation';
import PortfolioScores from '@/components/portfolio/PortfolioScores';
import { PortfolioRiskSimulator } from '@/components/portfolio/PortfolioRiskSimulator';
import AddTransactionButton from '@/components/portfolio/AddTransactionButton';
import RefreshPortfolioButton from '@/components/portfolio/RefreshPortfolioButton';
import { PortfolioChat } from '@/components/portfolio/PortfolioChat';
import { Wallet, LayoutDashboard, Briefcase, TrendingUp, TrendingDown, History, Brain, ShieldAlert, Activity } from 'lucide-react';
import type { PortfolioPerformanceHistory, PortfolioSummary as PortfolioSummaryType } from '@/lib/actions/portfolio.actions';

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
    userId: string;
};

export default function PortfolioTabs({ summary, transactions, scores, userId }: Props) {
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
        <div className="flex min-h-screen flex-col p-4 lg:p-6 max-w-[1600px] mx-auto">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-teal-500 to-blue-600 flex items-center justify-center">
                        <Wallet className="h-5 w-5 text-white" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-gray-100">Mi Cartera</h1>
                        <p className="text-sm text-gray-500">Seguimiento de tus inversiones</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Link className="inline-flex h-9 items-center gap-2 rounded-md border border-gray-700 px-3 text-sm text-gray-300 transition hover:border-teal-700 hover:text-teal-300" href="/portfolio/intelligence">
                        <Activity className="h-4 w-4" /> Intelligence
                    </Link>
                    <RefreshPortfolioButton userId={userId} />
                    <AddTransactionButton userId={userId} />
                </div>
            </div>

            {/* Tabs Navigation */}
            <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                <TabsList className="bg-[#0a0a0a] border border-gray-800 p-1 rounded-xl mb-6 w-fit">
                    <TabsTrigger
                        value="resumen"
                        className="data-[state=active]:bg-gray-800 data-[state=active]:text-white rounded-lg px-4 py-2 text-gray-400 flex items-center gap-2"
                    >
                        <LayoutDashboard className="h-4 w-4" />
                        Resumen
                    </TabsTrigger>
                    <TabsTrigger
                        value="posiciones"
                        className="data-[state=active]:bg-gray-800 data-[state=active]:text-white rounded-lg px-4 py-2 text-gray-400 flex items-center gap-2"
                    >
                        <Briefcase className="h-4 w-4" />
                        Posiciones
                    </TabsTrigger>
                    <TabsTrigger
                        value="movimientos"
                        className="data-[state=active]:bg-gray-800 data-[state=active]:text-white rounded-lg px-4 py-2 text-gray-400 flex items-center gap-2"
                    >
                        <History className="h-4 w-4" />
                        Movimientos
                    </TabsTrigger>
                    <TabsTrigger
                        value="estrategia"
                        className="data-[state=active]:bg-gray-800 data-[state=active]:text-white rounded-lg px-4 py-2 text-gray-400 flex items-center gap-2"
                    >
                        <Brain className="h-4 w-4" />
                        Factores
                    </TabsTrigger>
                    <TabsTrigger
                        value="riesgo"
                        className="data-[state=active]:bg-gray-800 data-[state=active]:text-white rounded-lg px-4 py-2 text-gray-400 flex items-center gap-2"
                    >
                        <ShieldAlert className="h-4 w-4" />
                        Riesgo
                    </TabsTrigger>
                </TabsList>

                {/* Tab: Resumen */}
                <TabsContent value="resumen" className="mt-0">
                    {/* Métricas en fila */}
                    <div className="mb-6">
                        <PortfolioSummary summary={summary} />
                    </div>

                    {/* Grid: gráfico de rendimiento + distribución */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* Panel Izquierdo: Gráfico de Rendimiento */}
                        <div className="bg-[#111111] border border-gray-800 rounded-2xl p-6">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-gray-400 text-sm font-medium">Rendimiento Total</h3>
                                <div className="flex gap-1">
                                    {['1S', '1M', '3M', '6M', 'YTD', '1A', 'Todo'].map((period) => (
                                        <button
                                            key={period}
                                            onClick={() => setChartPeriod(period)}
                                            className={`px-2 py-1 text-xs rounded transition-colors ${chartPeriod === period
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
                                    ${summary.totalValue.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                                </p>
                                <p className={`text-sm flex items-center gap-1 ${summary.totalGain >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {summary.totalGain >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                                    {summary.totalGain >= 0 ? '+' : ''}{summary.totalGainPercent.toFixed(2)}%
                                    <span className="text-gray-500">
                                        ({summary.totalGain >= 0 ? '+' : ''}${summary.totalGain.toLocaleString('en-US', { minimumFractionDigits: 2 })})
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
                                <ResponsiveContainer width="100%" height="100%">
                                    <AreaChart data={chartData} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                                        <defs>
                                            <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                                                <stop
                                                    offset="5%"
                                                    stopColor={summary.totalGain >= 0 ? '#14b8a6' : '#ef4444'}
                                                    stopOpacity={0.3}
                                                />
                                                <stop
                                                    offset="95%"
                                                    stopColor={summary.totalGain >= 0 ? '#14b8a6' : '#ef4444'}
                                                    stopOpacity={0}
                                                />
                                            </linearGradient>
                                        </defs>
                                        <XAxis
                                            dataKey="date"
                                            axisLine={false}
                                            tickLine={false}
                                            tick={{ fill: '#6b7280', fontSize: 10 }}
                                            interval="preserveStartEnd"
                                        />
                                        <YAxis
                                            hide
                                            domain={['dataMin - 50', 'dataMax + 50']}
                                        />
                                        <Tooltip
                                            contentStyle={{
                                                backgroundColor: '#1f2937',
                                                border: '1px solid #374151',
                                                borderRadius: '8px',
                                            }}
                                            labelStyle={{ color: '#9ca3af' }}
                                            formatter={(value: number) => [`$${value.toFixed(2)}`, 'Valor']}
                                        />
                                        <Area
                                            type="monotone"
                                            dataKey="value"
                                            stroke={summary.totalGain >= 0 ? '#14b8a6' : '#ef4444'}
                                            strokeWidth={2}
                                            fillOpacity={1}
                                            fill="url(#colorValue)"
                                        />
                                    </AreaChart>
                                </ResponsiveContainer>
                                )}
                            </div>
                        </div>

                        {/* Panel Derecho: Pie Chart Completo */}
                        <PortfolioAllocation
                            holdings={summary.holdings}
                            totalValue={summary.totalValue}
                        />
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

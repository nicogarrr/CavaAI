'use client';

import { useState, useMemo } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts';
import PortfolioSummary from '@/components/portfolio/PortfolioSummary';
import PortfolioHoldings from '@/components/portfolio/PortfolioHoldings';
import PortfolioTransactions from '@/components/portfolio/PortfolioTransactions';
import PortfolioAllocation from '@/components/portfolio/PortfolioAllocation';
import { PortfolioStrategyInsight } from '@/components/portfolio/PortfolioStrategyInsight';
import AddTransactionButton from '@/components/portfolio/AddTransactionButton';
import ImportFromImage from '@/components/portfolio/ImportFromImage';
import RefreshPortfolioButton from '@/components/portfolio/RefreshPortfolioButton';
import { PortfolioChat } from '@/components/portfolio/PortfolioChat';
import { Wallet, LayoutDashboard, Briefcase, TrendingUp, TrendingDown, History, Brain } from 'lucide-react';
import type { PortfolioSummary as PortfolioSummaryType } from '@/lib/actions/portfolio.actions';

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
    userId: string;
};

export default function PortfolioTabs({ summary, transactions, userId }: Props) {
    const [activeTab, setActiveTab] = useState('resumen');
    const [chartPeriod, setChartPeriod] = useState('1M');

    // Generar datos simulados para el gráfico basados en el valor actual y la ganancia
    const chartData = useMemo(() => {
        const periods: Record<string, number> = {
            '1S': 7,
            '1M': 30,
            '3M': 90,
            '6M': 180,
            'YTD': Math.floor((Date.now() - new Date(new Date().getFullYear(), 0, 1).getTime()) / (1000 * 60 * 60 * 24)),
            '1A': 365,
            'Todo': 365
        };

        const days = periods[chartPeriod] || 30;
        const data = [];
        const startValue = summary.totalCost; // Comenzamos desde el costo
        const endValue = summary.totalValue;  // Terminamos en el valor actual
        const volatility = 0.02; // 2% volatilidad diaria

        let currentValue = startValue;
        const dailyGrowth = (endValue - startValue) / days;

        for (let i = 0; i <= days; i++) {
            const date = new Date();
            date.setDate(date.getDate() - (days - i));

            // Añadir algo de variación realista
            const randomFactor = 1 + (Math.random() - 0.5) * volatility;
            currentValue = currentValue + dailyGrowth * randomFactor;

            // Asegurar que llegamos al valor final
            if (i === days) currentValue = endValue;

            data.push({
                date: date.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' }),
                value: Math.max(0, currentValue),
            });
        }

        return data;
    }, [summary.totalCost, summary.totalValue, chartPeriod]);
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
                    <RefreshPortfolioButton userId={userId} />
                    <ImportFromImage userId={userId} />
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
                        Estrategia AI
                    </TabsTrigger>
                </TabsList>

                {/* Tab: Resumen */}
                <TabsContent value="resumen" className="mt-0">
                    {/* Métricas en fila */}
                    <div className="mb-6">
                        <PortfolioSummary summary={summary} />
                    </div>

                    {/* Grid: Gráfico de rendimiento (placeholder) + Pie Chart completo */}
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

                {/* Tab: Estrategia AI */}
                <TabsContent value="estrategia" className="mt-0">
                    <PortfolioStrategyInsight portfolioSummary={summary} />
                </TabsContent>
            </Tabs>

            <PortfolioChat userId={userId} />
        </div>
    );
}

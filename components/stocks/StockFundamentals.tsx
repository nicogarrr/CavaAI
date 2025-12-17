'use client';

import { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import {
    BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
    Tooltip, Legend, ResponsiveContainer, ComposedChart, Area
} from 'recharts';
import { TrendingUp, DollarSign, PieChart, Activity, Loader2 } from 'lucide-react';
import { getFundamentals, getFinancialGrowth, type FundamentalsData, type GrowthData } from '@/lib/actions/fmp.actions';

interface StockFundamentalsProps {
    symbol: string;
}

const formatBillions = (value: number) => {
    if (Math.abs(value) >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
    if (Math.abs(value) >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
    return `$${value.toFixed(0)}`;
};

const formatPercent = (value: number) => `${(value * 100).toFixed(1)}%`;

const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
        return (
            <div className="bg-gray-900/95 border border-gray-700 rounded-lg p-3 shadow-xl">
                <p className="text-gray-300 font-medium mb-2">{label}</p>
                {payload.map((entry: any, index: number) => (
                    <p key={index} style={{ color: entry.color }} className="text-sm">
                        {entry.name}: {typeof entry.value === 'number'
                            ? entry.value > 1 ? formatBillions(entry.value) : formatPercent(entry.value)
                            : entry.value
                        }
                    </p>
                ))}
            </div>
        );
    }
    return null;
};

export default function StockFundamentals({ symbol }: StockFundamentalsProps) {
    const [fundamentals, setFundamentals] = useState<FundamentalsData | null>(null);
    const [growth, setGrowth] = useState<GrowthData[] | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchData() {
            try {
                setLoading(true);
                const [fundData, growthData] = await Promise.all([
                    getFundamentals(symbol),
                    getFinancialGrowth(symbol)
                ]);

                setFundamentals(fundData);
                setGrowth(growthData?.growth || null);
            } catch (err) {
                setError('Error loading fundamental data');
                console.error(err);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, [symbol]);

    if (loading) {
        return (
            <Card className="bg-gray-800/50 border-gray-700">
                <CardContent className="flex items-center justify-center h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-teal-400" />
                </CardContent>
            </Card>
        );
    }

    if (error || !fundamentals) {
        return (
            <Card className="bg-gray-800/50 border-gray-700">
                <CardContent className="flex items-center justify-center h-[400px]">
                    <p className="text-gray-400">{error || 'No data available'}</p>
                </CardContent>
            </Card>
        );
    }

    // Prepare chart data - reverse to show oldest first
    const incomeData = [...(fundamentals.income || [])].reverse().slice(0, 5).map(item => ({
        year: item.date.split('-')[0],
        revenue: item.revenue,
        grossProfit: item.grossProfit,
        netIncome: item.netIncome,
        grossMargin: item.grossProfitRatio,
        operatingMargin: item.operatingIncomeRatio,
        netMargin: item.netIncomeRatio,
    }));

    const balanceData = [...(fundamentals.balance || [])].reverse().slice(0, 5).map(item => ({
        year: item.date.split('-')[0],
        totalDebt: item.totalDebt,
        equity: item.totalStockholdersEquity,
        cash: item.cashAndCashEquivalents,
        assets: item.totalAssets,
    }));

    const growthChartData = [...(growth || [])].reverse().slice(0, 5).map(item => ({
        year: item.date.split('-')[0],
        revenueGrowth: item.revenueGrowth,
        epsGrowth: item.epsgrowth,
        fcfGrowth: item.freeCashFlowGrowth,
    }));

    return (
        <Card className="bg-gray-800/50 border-gray-700">
            <CardHeader className="pb-2">
                <CardTitle className="text-gray-100 flex items-center gap-2">
                    <Activity className="h-5 w-5 text-teal-400" />
                    Análisis Fundamental
                    <Badge variant="outline" className="ml-2 text-xs border-teal-500/30 text-teal-400">
                        FMP Data
                    </Badge>
                </CardTitle>
            </CardHeader>
            <CardContent>
                <Tabs defaultValue="revenue" className="w-full">
                    <TabsList className="grid w-full grid-cols-4 bg-gray-900/50">
                        <TabsTrigger value="revenue" className="text-xs data-[state=active]:bg-teal-600">
                            <DollarSign className="h-3 w-3 mr-1" />
                            Ingresos
                        </TabsTrigger>
                        <TabsTrigger value="margins" className="text-xs data-[state=active]:bg-teal-600">
                            <TrendingUp className="h-3 w-3 mr-1" />
                            Márgenes
                        </TabsTrigger>
                        <TabsTrigger value="debt" className="text-xs data-[state=active]:bg-teal-600">
                            <PieChart className="h-3 w-3 mr-1" />
                            Deuda
                        </TabsTrigger>
                        <TabsTrigger value="growth" className="text-xs data-[state=active]:bg-teal-600">
                            <Activity className="h-3 w-3 mr-1" />
                            Growth
                        </TabsTrigger>
                    </TabsList>

                    {/* Revenue Trend */}
                    <TabsContent value="revenue" className="mt-4">
                        <div className="h-[280px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <ComposedChart data={incomeData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis dataKey="year" stroke="#9CA3AF" fontSize={12} />
                                    <YAxis stroke="#9CA3AF" fontSize={10} tickFormatter={formatBillions} />
                                    <Tooltip content={<CustomTooltip />} />
                                    <Legend wrapperStyle={{ fontSize: '12px' }} />
                                    <Bar dataKey="revenue" name="Revenue" fill="#14b8a6" radius={[4, 4, 0, 0]} />
                                    <Bar dataKey="grossProfit" name="Gross Profit" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                                    <Line type="monotone" dataKey="netIncome" name="Net Income" stroke="#f59e0b" strokeWidth={2} dot={{ fill: '#f59e0b' }} />
                                </ComposedChart>
                            </ResponsiveContainer>
                        </div>
                    </TabsContent>

                    {/* Margins Evolution */}
                    <TabsContent value="margins" className="mt-4">
                        <div className="h-[280px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={incomeData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis dataKey="year" stroke="#9CA3AF" fontSize={12} />
                                    <YAxis stroke="#9CA3AF" fontSize={10} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                                    <Tooltip content={<CustomTooltip />} />
                                    <Legend wrapperStyle={{ fontSize: '12px' }} />
                                    <Line type="monotone" dataKey="grossMargin" name="Gross Margin" stroke="#14b8a6" strokeWidth={2} dot={{ fill: '#14b8a6' }} />
                                    <Line type="monotone" dataKey="operatingMargin" name="Operating Margin" stroke="#8b5cf6" strokeWidth={2} dot={{ fill: '#8b5cf6' }} />
                                    <Line type="monotone" dataKey="netMargin" name="Net Margin" stroke="#f59e0b" strokeWidth={2} dot={{ fill: '#f59e0b' }} />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    </TabsContent>

                    {/* Debt vs Equity */}
                    <TabsContent value="debt" className="mt-4">
                        <div className="h-[280px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={balanceData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis dataKey="year" stroke="#9CA3AF" fontSize={12} />
                                    <YAxis stroke="#9CA3AF" fontSize={10} tickFormatter={formatBillions} />
                                    <Tooltip content={<CustomTooltip />} />
                                    <Legend wrapperStyle={{ fontSize: '12px' }} />
                                    <Bar dataKey="totalDebt" name="Total Debt" fill="#ef4444" stackId="a" radius={[0, 0, 0, 0]} />
                                    <Bar dataKey="equity" name="Equity" fill="#22c55e" stackId="a" radius={[4, 4, 0, 0]} />
                                    <Bar dataKey="cash" name="Cash" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </TabsContent>

                    {/* Growth Rates */}
                    <TabsContent value="growth" className="mt-4">
                        <div className="h-[280px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={growthChartData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis dataKey="year" stroke="#9CA3AF" fontSize={12} />
                                    <YAxis stroke="#9CA3AF" fontSize={10} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                                    <Tooltip content={<CustomTooltip />} />
                                    <Legend wrapperStyle={{ fontSize: '12px' }} />
                                    <Bar dataKey="revenueGrowth" name="Revenue Growth" fill="#14b8a6" radius={[4, 4, 0, 0]} />
                                    <Bar dataKey="epsGrowth" name="EPS Growth" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                                    <Bar dataKey="fcfGrowth" name="FCF Growth" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </TabsContent>
                </Tabs>
            </CardContent>
        </Card>
    );
}

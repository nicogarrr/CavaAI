'use client';

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import type { PortfolioHolding } from '@/lib/actions/portfolio.actions';
import { PieChart as PieChartIcon } from 'lucide-react';

type Props = {
    holdings: PortfolioHolding[];
    totalValue: number;
};

// Paleta de colores vibrantes para el pie chart
const COLORS = [
    '#14b8a6', // teal-500
    '#8b5cf6', // violet-500
    '#f59e0b', // amber-500
    '#ef4444', // red-500
    '#3b82f6', // blue-500
    '#ec4899', // pink-500
    '#22c55e', // green-500
    '#f97316', // orange-500
    '#06b6d4', // cyan-500
    '#a855f7', // purple-500
    '#eab308', // yellow-500
    '#6366f1', // indigo-500
];

interface CustomTooltipProps {
    active?: boolean;
    payload?: Array<{
        name: string;
        value: number;
        payload: {
            symbol: string;
            value: number;
            percentage: number;
            gain: number;
            gainPercent: number;
        };
    }>;
}

const CustomTooltip = ({ active, payload }: CustomTooltipProps) => {
    if (active && payload && payload.length) {
        const data = payload[0].payload;
        const isPositive = data.gain >= 0;

        return (
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-xl">
                <p className="font-bold text-teal-400 mb-1">{data.symbol}</p>
                <p className="text-gray-300 text-sm">
                    Valor: <span className="font-semibold text-white">${data.value.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                </p>
                <p className="text-gray-300 text-sm">
                    Peso: <span className="font-semibold text-white">{data.percentage.toFixed(1)}%</span>
                </p>
                <p className="text-gray-300 text-sm">
                    G/P: <span className={`font-semibold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                        {isPositive ? '+' : ''}{data.gainPercent.toFixed(2)}%
                    </span>
                </p>
            </div>
        );
    }
    return null;
};

interface LegendPayloadItem {
    value: string;
    color?: string;
    payload?: {
        percentage: number;
    };
}

interface CustomLegendProps {
    payload?: LegendPayloadItem[];
}

const CustomLegend = ({ payload }: CustomLegendProps) => {
    if (!payload) return null;

    return (
        <div className="flex flex-wrap justify-center gap-3 mt-4">
            {payload.map((entry, index) => (
                <div key={`legend-${index}`} className="flex items-center gap-2">
                    <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: entry.color }}
                    />
                    <span className="text-sm text-gray-300">
                        {entry.value} ({entry.payload?.percentage?.toFixed(1)}%)
                    </span>
                </div>
            ))}
        </div>
    );
};

export default function PortfolioAllocation({ holdings, totalValue }: Props) {
    if (holdings.length === 0) {
        return (
            <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader className="pb-2">
                    <CardTitle className="text-gray-100 flex items-center gap-2">
                        <PieChartIcon className="h-5 w-5 text-teal-400" />
                        Distribución del Portfolio
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="text-center py-8">
                        <p className="text-gray-400">Añade posiciones para ver la distribución</p>
                    </div>
                </CardContent>
            </Card>
        );
    }

    // Preparar datos para el pie chart
    const chartData = holdings
        .map((holding) => ({
            symbol: holding.symbol,
            value: holding.value,
            percentage: (holding.value / totalValue) * 100,
            gain: holding.gain,
            gainPercent: holding.gainPercent,
        }))
        .sort((a, b) => b.value - a.value); // Ordenar por valor descendente

    return (
        <div className="bg-[#111111] border border-gray-800 rounded-2xl p-6 h-full flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between mb-2">
                <span className="text-gray-400 text-sm font-medium">Distribución</span>
            </div>

            {/* Contenido: Pie Chart + Leyenda */}
            <div className="flex-1 flex items-center justify-between">
                {/* Pie Chart - Más grande */}
                <div className="relative w-[250px] h-[250px] flex-shrink-0">
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={chartData}
                                cx="50%"
                                cy="50%"
                                innerRadius={70}
                                outerRadius={105}
                                paddingAngle={2}
                                dataKey="value"
                                nameKey="symbol"
                                animationBegin={0}
                                animationDuration={800}
                            >
                                {chartData.map((entry, index) => (
                                    <Cell
                                        key={`cell-${entry.symbol}`}
                                        fill={COLORS[index % COLORS.length]}
                                        stroke="rgba(0,0,0,0)"
                                        strokeWidth={0}
                                    />
                                ))}
                            </Pie>
                            <Tooltip content={<CustomTooltip />} />
                        </PieChart>
                    </ResponsiveContainer>

                    {/* Centro del Donut */}
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <div className="text-center">
                            <span className="text-4xl font-bold text-white block">{holdings.length}</span>
                            <span className="text-xs text-gray-500">Posiciones</span>
                        </div>
                    </div>
                </div>

                {/* Leyenda lateral - Pegada a la derecha */}
                <div className="space-y-3 overflow-y-auto max-h-[250px] min-w-[140px]">
                    {chartData.map((item, index) => (
                        <div key={item.symbol} className="flex items-center justify-between gap-6">
                            <div className="flex items-center gap-2">
                                <div
                                    className="w-3 h-3 rounded-full"
                                    style={{ backgroundColor: COLORS[index % COLORS.length] }}
                                />
                                <span className="text-sm text-gray-300">{item.symbol}</span>
                            </div>
                            <span className="text-sm text-gray-400 tabular-nums">
                                {item.percentage.toFixed(1)}%
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

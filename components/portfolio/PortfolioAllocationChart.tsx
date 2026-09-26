'use client';

import Link from 'next/link';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

import { formatMoney, formatPercent } from '@/lib/format';

export type AllocationSlice = {
    symbol: string;
    value: number;
    percentage: number;
    gain: number;
    gainPercent: number;
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
        payload: AllocationSlice;
    }>;
}

const CustomTooltip = ({ active, payload }: CustomTooltipProps) => {
    if (active && payload && payload.length) {
        const data = payload[0].payload;
        const isPositive = data.gain >= 0;

        return (
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-xl">
                <Link href={`/research/${data.symbol}`} className="font-bold text-teal-400 hover:text-teal-300 mb-1 block">
                    {data.symbol}
                </Link>
                <p className="text-gray-300 text-sm">
                    Valor: <span className="font-semibold text-white">{formatMoney(data.value)}</span>
                </p>
                <p className="text-gray-300 text-sm">
                    Peso: <span className="font-semibold text-white">{formatPercent(data.percentage, { fromRatio: false, digits: 1 })}</span>
                </p>
                <p className="text-gray-300 text-sm">
                    G/P: <span className={`font-semibold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                        {formatPercent(data.gainPercent, { fromRatio: false, digits: 2, signDisplay: 'always' })}
                    </span>
                </p>
            </div>
        );
    }
    return null;
};

/** Donut de distribución: se carga solo en cliente (dynamic ssr:false desde el panel) */
export default function PortfolioAllocationChart({ chartData }: { chartData: AllocationSlice[] }) {
    return (
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
    );
}

export { COLORS };

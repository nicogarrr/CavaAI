'use client';

import Link from 'next/link';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

import { AllocationTooltip } from './AllocationTooltip';
import { buildAllocationSlices, CASH_SLICE_SYMBOL, type AllocationSliceData } from '@/lib/portfolio-allocation';

export type AllocationSlice = AllocationSliceData;
export { buildAllocationSlices, CASH_SLICE_SYMBOL };

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

/** Donut de distribución: se carga solo en cliente (dynamic ssr:false desde el panel) */
export default function PortfolioAllocationChart({ chartData, currency }: { chartData: AllocationSlice[]; currency?: string }) {
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
                <Tooltip content={<AllocationTooltip currency={currency} />} />
            </PieChart>
        </ResponsiveContainer>
    );
}

export { COLORS };

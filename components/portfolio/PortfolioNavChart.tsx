'use client';

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export type NavPoint = {
    date: string;
    value: number;
};

type Props = {
    data: NavPoint[];
    positive: boolean;
};

/** Gráfico de área del NAV (carga diferida: recharts no va al bundle inicial). */
export default function PortfolioNavChart({ data, positive }: Props) {
    const color = positive ? '#14b8a6' : '#ef4444';
    return (
        <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={color} stopOpacity={0} />
                    </linearGradient>
                </defs>
                <XAxis
                    dataKey="date"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#6b7280', fontSize: 10 }}
                    interval="preserveStartEnd"
                />
                <YAxis hide domain={['dataMin - 50', 'dataMax + 50']} />
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
                    stroke={color}
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#colorValue)"
                />
            </AreaChart>
        </ResponsiveContainer>
    );
}

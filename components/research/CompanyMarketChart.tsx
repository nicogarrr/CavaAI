'use client';

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { formatMoney } from '@/lib/format';
import type { CompanyMarketSnapshot } from '@/lib/actions/market-workspace.actions';

function money(value: number | null) {
    return value == null ? 'N/A' : formatMoney(value, 'USD');
}

/** Gráfico de historial: se carga solo en cliente (dynamic ssr:false desde el panel) */
export default function CompanyMarketChart({ history }: { history: CompanyMarketSnapshot['history'] }) {
    return (
        <div className="h-[280px] w-full sm:h-[420px]">
            <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={history}>
                    <defs>
                        <linearGradient id="marketPrice" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#2dd4bf" stopOpacity={0.35} />
                            <stop offset="95%" stopColor="#2dd4bf" stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#1f2937" vertical={false} />
                    <XAxis dataKey="date" minTickGap={48} stroke="#6b7280" />
                    <YAxis domain={['auto', 'auto']} stroke="#6b7280" />
                    <Tooltip
                        contentStyle={{ background: '#111827', border: '1px solid #374151' }}
                        formatter={(value: number) => [money(value), 'Cierre']}
                    />
                    <Area type="monotone" dataKey="close" stroke="#2dd4bf" fill="url(#marketPrice)" strokeWidth={2} />
                </AreaChart>
            </ResponsiveContainer>
        </div>
    );
}

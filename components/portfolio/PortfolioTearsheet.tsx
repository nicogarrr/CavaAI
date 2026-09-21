'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Gauge, TrendingDown, Target } from 'lucide-react';
import type { PortfolioTearsheet } from '@/lib/actions/portfolio.actions';

type Props = {
    tearsheet: PortfolioTearsheet | null;
};

function formatMetric(value: number | null, digits = 2): string {
    return value === null || value === undefined || !Number.isFinite(value) ? 'N/D' : value.toFixed(digits);
}

function formatPercent(value: number | null, digits = 2): string {
    return value === null || value === undefined || !Number.isFinite(value) ? 'N/D' : `${(value * 100).toFixed(digits)}%`;
}

export default function PortfolioTearsheet({ tearsheet }: Props) {
    const metrics = tearsheet?.metrics ?? null;

    if (!tearsheet || !metrics || metrics.n_observations < 2) {
        return (
            <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader className="pb-2">
                    <CardTitle className="text-lg text-gray-100">Tearsheet</CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-sm text-gray-400">
                        Sin historial suficiente para calcular Sharpe, drawdown o win rate. Importa tu cartera desde
                        IBKR o registra movimientos para generar snapshots.
                    </p>
                </CardContent>
            </Card>
        );
    }

    const sharpePositive = (metrics.sharpe ?? 0) >= 0;
    const items = [
        { label: 'Sharpe', value: formatMetric(metrics.sharpe), icon: Gauge, color: sharpePositive ? 'text-green-400' : 'text-red-400' },
        { label: 'Max Drawdown', value: formatPercent(metrics.max_drawdown), icon: TrendingDown, color: 'text-orange-400' },
        { label: 'Win Rate', value: formatPercent(metrics.win_rate), icon: Target, color: 'text-blue-400' },
    ];

    return (
        <Card className="bg-gray-800/50 border-gray-700">
            <CardHeader className="pb-2">
                <CardTitle className="text-lg text-gray-100">Tearsheet</CardTitle>
            </CardHeader>
            <CardContent>
                <div className="grid grid-cols-3 gap-4">
                    {items.map((item) => (
                        <div key={item.label} className="text-center p-3 bg-gray-900/50 rounded-lg">
                            <item.icon className={`h-6 w-6 mx-auto mb-2 ${item.color}`} />
                            <div className="text-2xl font-bold text-gray-100">{item.value}</div>
                            <div className="text-xs text-gray-400">{item.label}</div>
                        </div>
                    ))}
                </div>
                <p className="mt-3 text-xs text-gray-500">
                    {metrics.n_observations} sesiones · Ret. acumulado {formatPercent(metrics.cumulative_return)} ·
                    Mejor día {formatPercent(metrics.best_day)} · Peor día {formatPercent(metrics.worst_day)}
                    {tearsheet.exposure ? ` · ${tearsheet.exposure.n_positions} posiciones` : ''}
                </p>
            </CardContent>
        </Card>
    );
}

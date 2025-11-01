'use client';

import { TrendingUp, TrendingDown } from 'lucide-react';

type PortfolioSummaryProps = {
    summary: {
        totalInvested: number;
        totalCurrentValue: number;
        totalProfitLoss: number;
        totalProfitLossPercent: number;
        positionCount: number;
    };
};

export default function PortfolioSummary({ summary }: PortfolioSummaryProps) {
    const formatCurrency = (value: number) => {
        return new Intl.NumberFormat('es-ES', {
            style: 'currency',
            currency: 'USD',
        }).format(value);
    };

    const isProfit = summary.totalProfitLoss >= 0;

    return (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            <div className="border rounded-lg p-6">
                <p className="text-sm text-muted-foreground mb-2">Valor Invertido</p>
                <p className="text-2xl font-bold">{formatCurrency(summary.totalInvested)}</p>
            </div>

            <div className="border rounded-lg p-6">
                <p className="text-sm text-muted-foreground mb-2">Valor Actual</p>
                <p className="text-2xl font-bold">{formatCurrency(summary.totalCurrentValue)}</p>
            </div>

            <div className="border rounded-lg p-6">
                <p className="text-sm text-muted-foreground mb-2">Ganancia/Pérdida</p>
                <div className="flex items-center gap-2">
                    {isProfit ? (
                        <TrendingUp className="h-5 w-5 text-green-500" />
                    ) : (
                        <TrendingDown className="h-5 w-5 text-red-500" />
                    )}
                    <p className={`text-2xl font-bold ${isProfit ? 'text-green-500' : 'text-red-500'}`}>
                        {formatCurrency(summary.totalProfitLoss)}
                    </p>
                </div>
                <p className={`text-sm mt-1 ${isProfit ? 'text-green-500' : 'text-red-500'}`}>
                    {isProfit ? '+' : ''}{summary.totalProfitLossPercent.toFixed(2)}%
                </p>
            </div>

            <div className="border rounded-lg p-6">
                <p className="text-sm text-muted-foreground mb-2">Posiciones</p>
                <p className="text-2xl font-bold">{summary.positionCount}</p>
            </div>
        </div>
    );
}


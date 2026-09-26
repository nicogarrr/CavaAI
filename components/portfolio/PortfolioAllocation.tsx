'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import type { PortfolioHolding } from '@/lib/actions/portfolio.actions';
import { PieChart as PieChartIcon } from 'lucide-react';
import { formatPercent } from '@/lib/format';
import { COLORS, type AllocationSlice } from './PortfolioAllocationChart';

const PortfolioAllocationChart = dynamic(() => import('./PortfolioAllocationChart'), {
    ssr: false,
    loading: () => (
        <div className="h-[250px] w-[250px] animate-pulse rounded-full border border-gray-800 bg-gray-900/40" aria-label="Cargando distribución" role="status" />
    ),
});

type Props = {
    holdings: PortfolioHolding[];
    totalValue: number;
};

export default function PortfolioAllocation({ holdings, totalValue }: Props) {
    if (holdings.length === 0) {
        return (
            <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader className="pb-2">
                    <CardTitle className="text-gray-100 flex items-center gap-2">
                        <PieChartIcon className="h-5 w-5 text-teal-400" />
                        Distribución de la cartera
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
    const chartData: AllocationSlice[] = holdings
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
                    <PortfolioAllocationChart chartData={chartData} />

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
                                <Link
                                    href={`/research/${item.symbol}`}
                                    className="text-sm text-gray-300 hover:text-teal-300 transition-colors"
                                >
                                    {item.symbol}
                                </Link>
                            </div>
                            <span className="text-sm text-gray-400 tabular-nums">
                                {formatPercent(item.percentage, { fromRatio: false, digits: 1 })}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

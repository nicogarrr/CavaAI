'use client';

import { Card } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface SectorComparisonChartProps {
    categoryScores: {
        value: number;
        growth: number;
        profitability: number;
        cashFlow: number;
        momentum: number;
        debtLiquidity: number;
    };
    sectorAverages: {
        value: number;
        growth: number;
        profitability: number;
        cashFlow: number;
        momentum: number;
        debtLiquidity: number;
    };
    vsSector: {
        value: number;
        growth: number;
        profitability: number;
        cashFlow: number;
        momentum: number;
        debtLiquidity: number;
    };
    sector: string;
}

const categoryLabels: Record<string, string> = {
    value: 'Valor Relativo',
    growth: 'Crecimiento',
    profitability: 'Rentabilidad',
    cashFlow: 'Flujo de Caja',
    momentum: 'Impulso',
    debtLiquidity: 'Deuda/Liquidez',
};

export default function SectorComparisonChart({
    categoryScores,
    sectorAverages,
    vsSector,
    sector,
}: SectorComparisonChartProps) {
    const categories = Object.keys(categoryScores) as Array<keyof typeof categoryScores>;

    const getVsSectorIcon = (vs: number) => {
        if (vs > 5) return <TrendingUp className="h-4 w-4 text-green-400" />;
        if (vs < -5) return <TrendingDown className="h-4 w-4 text-red-400" />;
        return <Minus className="h-4 w-4 text-gray-500" />;
    };

    const getVsSectorColor = (vs: number) => {
        if (vs > 10) return 'text-green-400';
        if (vs > 5) return 'text-green-500';
        if (vs < -10) return 'text-red-400';
        if (vs < -5) return 'text-red-500';
        return 'text-gray-400';
    };

    return (
        <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
            <div className="mb-6">
                <h3 className="text-xl font-bold text-gray-100 mb-2">Comparación con Sector</h3>
                <p className="text-sm text-gray-400">
                    Comparación de métricas con el promedio del sector <span className="font-semibold text-teal-400">{sector}</span>
                </p>
            </div>

            <div className="space-y-6">
                {categories.map((category) => {
                    const stockScore = categoryScores[category];
                    const sectorAvg = sectorAverages[category];
                    const vs = vsSector[category];

                    return (
                        <div key={category} className="space-y-2">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <span className="text-sm font-medium text-gray-300">
                                        {categoryLabels[category]}
                                    </span>
                                    {getVsSectorIcon(vs)}
                                </div>
                                <div className="flex items-center gap-4">
                                    <div className="text-right">
                                        <div className="text-sm font-bold text-gray-100">
                                            {stockScore.toFixed(0)}
                                        </div>
                                        <div className="text-xs text-gray-500">Acción</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-sm font-medium text-gray-400">
                                            {sectorAvg.toFixed(0)}
                                        </div>
                                        <div className="text-xs text-gray-500">Sector</div>
                                    </div>
                                    <div className={`text-right min-w-[60px] ${getVsSectorColor(vs)}`}>
                                        <div className="text-sm font-bold">
                                            {vs > 0 ? '+' : ''}{vs.toFixed(0)}
                                        </div>
                                        <div className="text-xs">vs Sector</div>
                                    </div>
                                </div>
                            </div>

                            {/* Barra de progreso comparativa */}
                            <div className="space-y-1">
                                <div className="relative h-4 bg-gray-900 rounded-full overflow-hidden">
                                    {/* Fondo sector */}
                                    <div
                                        className="absolute h-full bg-gray-700/50 rounded-full"
                                        style={{ width: `${Math.min(100, sectorAvg)}%` }}
                                    />
                                    {/* Acción */}
                                    <div
                                        className="absolute h-full bg-teal-500 rounded-full transition-all"
                                        style={{ width: `${Math.min(100, stockScore)}%` }}
                                    />
                                </div>
                                <div className="flex justify-between text-xs text-gray-500">
                                    <span>0</span>
                                    <span>50</span>
                                    <span>100</span>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            <div className="mt-6 p-4 bg-gray-900/50 rounded-lg border border-gray-700/50">
                <h4 className="text-sm font-semibold text-gray-300 mb-3">Interpretación</h4>
                <div className="space-y-2 text-xs text-gray-400">
                    <div className="flex items-start gap-2">
                        <TrendingUp className="h-3 w-3 text-green-400 mt-0.5 flex-shrink-0" />
                        <span>Verde (+10 o más): Significativamente mejor que el sector</span>
                    </div>
                    <div className="flex items-start gap-2">
                        <Minus className="h-3 w-3 text-gray-500 mt-0.5 flex-shrink-0" />
                        <span>Gris (-5 a +5): Similar al promedio del sector</span>
                    </div>
                    <div className="flex items-start gap-2">
                        <TrendingDown className="h-3 w-3 text-red-400 mt-0.5 flex-shrink-0" />
                        <span>Rojo (-10 o menos): Por debajo del promedio del sector</span>
                    </div>
                </div>
            </div>
        </Card>
    );
}


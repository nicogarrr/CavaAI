'use client';

import { useEffect, useState } from 'react';
import { getAnalystEstimates, AnalystEstimate } from '@/lib/actions/fmp.actions';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { TrendingUp, DollarSign, Loader2, Target } from 'lucide-react';

interface AnalystEstimatesPanelProps {
    symbol: string;
}

export default function AnalystEstimatesPanel({ symbol }: AnalystEstimatesPanelProps) {
    const [estimates, setEstimates] = useState<AnalystEstimate[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchData() {
            try {
                setLoading(true);
                const data = await getAnalystEstimates(symbol, 'annual', 5);
                setEstimates(data?.estimates || []);
            } catch (err) {
                console.error('Error fetching analyst estimates:', err);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, [symbol]);

    const formatRevenue = (num: number | undefined | null) => {
        if (num === undefined || num === null) return 'N/A';
        if (num >= 1e12) return `$${(num / 1e12).toFixed(2)}T`;
        if (num >= 1e9) return `$${(num / 1e9).toFixed(2)}B`;
        if (num >= 1e6) return `$${(num / 1e6).toFixed(2)}M`;
        return `$${num.toFixed(2)}`;
    };

    const formatEps = (num: number | undefined | null) => {
        if (num === undefined || num === null) return 'N/A';
        return `$${num.toFixed(2)}`;
    };

    const getYear = (dateStr: string) => new Date(dateStr).getFullYear();

    if (loading) {
        return (
            <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader>
                    <CardTitle className="text-gray-100 flex items-center gap-2">
                        <Target className="h-5 w-5 text-purple-400" />
                        Estimaciones de Analistas
                        <Loader2 className="h-4 w-4 animate-spin ml-auto text-gray-400" />
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                    <Skeleton className="h-20 w-full bg-gray-700" />
                    <Skeleton className="h-20 w-full bg-gray-700" />
                </CardContent>
            </Card>
        );
    }

    if (estimates.length === 0) {
        return (
            <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader>
                    <CardTitle className="text-gray-100 flex items-center gap-2">
                        <Target className="h-5 w-5 text-purple-400" />
                        Estimaciones de Analistas
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-sm text-gray-500 text-center py-4">
                        No hay estimaciones disponibles
                    </p>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="bg-gray-800/50 border-gray-700">
            <CardHeader>
                <CardTitle className="text-gray-100 flex items-center gap-2">
                    <Target className="h-5 w-5 text-purple-400" />
                    Estimaciones de Analistas
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Estimates Table */}
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-gray-700">
                                <th className="text-left py-2 px-2 text-gray-400 font-medium">Año</th>
                                <th className="text-right py-2 px-2 text-gray-400 font-medium">Revenue</th>
                                <th className="text-right py-2 px-2 text-gray-400 font-medium">EPS</th>
                                <th className="text-right py-2 px-2 text-gray-400 font-medium">Analistas</th>
                            </tr>
                        </thead>
                        <tbody>
                            {estimates.map((est, idx) => (
                                <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                                    <td className="py-3 px-2">
                                        <span className="text-gray-100 font-semibold">{getYear(est.date)}</span>
                                    </td>
                                    <td className="py-3 px-2 text-right">
                                        <div className="text-gray-100">{formatRevenue(est.estimatedRevenueAvg)}</div>
                                        <div className="text-xs text-gray-500">
                                            {formatRevenue(est.estimatedRevenueLow)} - {formatRevenue(est.estimatedRevenueHigh)}
                                        </div>
                                    </td>
                                    <td className="py-3 px-2 text-right">
                                        <div className="text-teal-400 font-semibold">{formatEps(est.estimatedEpsAvg)}</div>
                                        <div className="text-xs text-gray-500">
                                            {formatEps(est.estimatedEpsLow)} - {formatEps(est.estimatedEpsHigh)}
                                        </div>
                                    </td>
                                    <td className="py-3 px-2 text-right">
                                        <span className="text-gray-300">{est.numberAnalystsEstimatedEps || est.numberAnalystEstimatedRevenue}</span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* EPS Trend Visualization */}
                <div className="mt-4 pt-4 border-t border-gray-700">
                    <h4 className="text-xs font-semibold text-gray-400 uppercase mb-3">Tendencia EPS Proyectado</h4>
                    <div className="flex items-end justify-between gap-2 h-24">
                        {estimates.slice().reverse().map((est, idx) => {
                            const maxEps = Math.max(...estimates.map(e => e.estimatedEpsAvg || 0));
                            const height = maxEps > 0 ? ((est.estimatedEpsAvg || 0) / maxEps) * 100 : 0;
                            return (
                                <div key={idx} className="flex-1 flex flex-col items-center gap-1">
                                    <span className="text-xs text-teal-400 font-medium">
                                        {formatEps(est.estimatedEpsAvg)}
                                    </span>
                                    <div
                                        className="w-full bg-gradient-to-t from-teal-600 to-teal-400 rounded-t"
                                        style={{ height: `${Math.max(10, height)}%` }}
                                    />
                                    <span className="text-xs text-gray-500">{getYear(est.date)}</span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

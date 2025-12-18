'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { TrendingUp, TrendingDown, DollarSign, Percent, Users, Building2 } from 'lucide-react';

type EconomicDataPoint = {
    date: string;
    value: number;
};

type EconomicIndicator = {
    name: string;
    interval: string;
    unit: string;
    data: EconomicDataPoint[];
};

type AllIndicators = {
    gdp: EconomicIndicator | null;
    cpi: EconomicIndicator | null;
    unemployment: EconomicIndicator | null;
    federalFundsRate: EconomicIndicator | null;
    treasuryYield10Y: EconomicIndicator | null;
    inflation: EconomicIndicator | null;
};

export default function EconomicIndicatorsPanel() {
    const [indicators, setIndicators] = useState<AllIndicators | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchIndicators() {
            setLoading(true);
            try {
                const { getAllEconomicIndicators } = await import('@/lib/actions/alphaVantage.actions');
                const data = await getAllEconomicIndicators();
                setIndicators(data);
                setError(null);
            } catch (err) {
                console.error('Error fetching economic indicators:', err);
                setError('Error al cargar indicadores económicos');
            } finally {
                setLoading(false);
            }
        }
        fetchIndicators();
    }, []);

    if (loading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Building2 className="h-5 w-5" />
                        Indicadores Económicos
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                        {[1, 2, 3, 4, 5, 6].map((i) => (
                            <Skeleton key={i} className="h-24 w-full" />
                        ))}
                    </div>
                </CardContent>
            </Card>
        );
    }

    if (error || !indicators) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Building2 className="h-5 w-5" />
                        Indicadores Económicos
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-muted-foreground text-center py-6">
                        {error || 'No hay datos de indicadores económicos disponibles'}
                    </p>
                </CardContent>
            </Card>
        );
    }

    const indicatorCards = [
        {
            key: 'gdp',
            data: indicators.gdp,
            icon: DollarSign,
            color: 'text-green-500',
            bgColor: 'bg-green-500/10',
        },
        {
            key: 'cpi',
            data: indicators.cpi,
            icon: Percent,
            color: 'text-blue-500',
            bgColor: 'bg-blue-500/10',
        },
        {
            key: 'unemployment',
            data: indicators.unemployment,
            icon: Users,
            color: 'text-orange-500',
            bgColor: 'bg-orange-500/10',
        },
        {
            key: 'federalFundsRate',
            data: indicators.federalFundsRate,
            icon: Building2,
            color: 'text-purple-500',
            bgColor: 'bg-purple-500/10',
        },
        {
            key: 'treasuryYield10Y',
            data: indicators.treasuryYield10Y,
            icon: TrendingUp,
            color: 'text-cyan-500',
            bgColor: 'bg-cyan-500/10',
        },
        {
            key: 'inflation',
            data: indicators.inflation,
            icon: TrendingDown,
            color: 'text-red-500',
            bgColor: 'bg-red-500/10',
        },
    ];

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Building2 className="h-5 w-5" />
                    Indicadores Económicos (EE.UU.)
                </CardTitle>
                <CardDescription>
                    Datos macroeconómicos de la Reserva Federal
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    {indicatorCards.map(({ key, data, icon: Icon, color, bgColor }) => {
                        if (!data || !data.data?.[0]) return null;

                        const latest = data.data[0];
                        const previous = data.data[1];
                        const change = previous ? ((latest.value - previous.value) / previous.value * 100) : 0;
                        const isPositive = change >= 0;

                        return (
                            <div
                                key={key}
                                className={`p-4 rounded-lg border ${bgColor} transition-all hover:scale-[1.02]`}
                            >
                                <div className="flex items-center gap-2 mb-2">
                                    <Icon className={`h-4 w-4 ${color}`} />
                                    <span className="text-xs font-medium text-muted-foreground truncate">
                                        {data.name}
                                    </span>
                                </div>
                                <div className="flex items-baseline gap-2">
                                    <span className="text-2xl font-bold">
                                        {data.unit === 'percent'
                                            ? `${latest.value.toFixed(2)}%`
                                            : data.unit === 'billions of dollars'
                                                ? `$${(latest.value / 1000).toFixed(1)}T`
                                                : latest.value.toFixed(2)
                                        }
                                    </span>
                                    {previous && (
                                        <span className={`text-xs flex items-center ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
                                            {isPositive ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                                            {Math.abs(change).toFixed(1)}%
                                        </span>
                                    )}
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    {new Date(latest.date).toLocaleDateString('es-ES', {
                                        month: 'short',
                                        year: 'numeric'
                                    })}
                                </p>
                            </div>
                        );
                    })}
                </div>
            </CardContent>
        </Card>
    );
}

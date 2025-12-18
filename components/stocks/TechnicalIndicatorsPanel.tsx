'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Activity, TrendingUp, TrendingDown, Minus, BarChart3, LineChart } from 'lucide-react';

type TechnicalIndicatorValue = {
    datetime: string;
    value: number;
};

type TechnicalIndicatorResponse = {
    symbol: string;
    indicator: string;
    values: TechnicalIndicatorValue[];
};

interface TechnicalIndicatorsPanelProps {
    symbol: string;
}

function getSignal(indicator: string, value: number): { signal: 'buy' | 'sell' | 'neutral'; label: string } {
    switch (indicator) {
        case 'RSI':
            if (value >= 70) return { signal: 'sell', label: 'Sobrecomprado' };
            if (value <= 30) return { signal: 'buy', label: 'Sobrevendido' };
            return { signal: 'neutral', label: 'Neutral' };
        case 'ADX':
            if (value >= 25) return { signal: 'buy', label: 'Tendencia fuerte' };
            return { signal: 'neutral', label: 'Sin tendencia' };
        default:
            return { signal: 'neutral', label: 'Neutral' };
    }
}

export default function TechnicalIndicatorsPanel({ symbol }: TechnicalIndicatorsPanelProps) {
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchIndicators() {
            setLoading(true);
            try {
                const { getAllTechnicalIndicators } = await import('@/lib/actions/twelveData.actions');
                const result = await getAllTechnicalIndicators(symbol, '1day');
                setData(result);
                setError(null);
            } catch (err) {
                console.error('Error fetching technical indicators:', err);
                setError('Error al cargar indicadores técnicos');
            } finally {
                setLoading(false);
            }
        }
        fetchIndicators();
    }, [symbol]);

    if (loading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Activity className="h-5 w-5" />
                        Indicadores Técnicos
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
                            <Skeleton key={i} className="h-20 w-full" />
                        ))}
                    </div>
                </CardContent>
            </Card>
        );
    }

    if (error || !data) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Activity className="h-5 w-5" />
                        Indicadores Técnicos
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-muted-foreground text-center py-6">
                        {error || `No hay indicadores técnicos disponibles para ${symbol}`}
                    </p>
                </CardContent>
            </Card>
        );
    }

    // Simple indicators (single value)
    const simpleIndicators = [
        { key: 'rsi', label: 'RSI (14)', data: data.rsi },
        { key: 'adx', label: 'ADX (14)', data: data.adx },
        { key: 'atr', label: 'ATR (14)', data: data.atr },
        { key: 'sma20', label: 'SMA (20)', data: data.sma20 },
        { key: 'sma50', label: 'SMA (50)', data: data.sma50 },
        { key: 'ema12', label: 'EMA (12)', data: data.ema12 },
        { key: 'ema26', label: 'EMA (26)', data: data.ema26 },
    ];

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Activity className="h-5 w-5" />
                    Indicadores Técnicos
                </CardTitle>
                <CardDescription>
                    Análisis técnico basado en TwelveData
                </CardDescription>
            </CardHeader>
            <CardContent>
                <Tabs defaultValue="momentum" className="w-full">
                    <TabsList className="grid w-full grid-cols-3">
                        <TabsTrigger value="momentum">Momentum</TabsTrigger>
                        <TabsTrigger value="trend">Tendencia</TabsTrigger>
                        <TabsTrigger value="volatility">Volatilidad</TabsTrigger>
                    </TabsList>

                    <TabsContent value="momentum" className="mt-4">
                        <div className="grid grid-cols-2 gap-4">
                            {/* RSI */}
                            {data.rsi?.values?.[0] && (
                                <IndicatorCard
                                    label="RSI (14)"
                                    value={data.rsi.values[0].value}
                                    format="number"
                                    signal={getSignal('RSI', data.rsi.values[0].value)}
                                />
                            )}

                            {/* Stochastic */}
                            {data.stochastic?.values?.[0] && (
                                <div className="p-4 rounded-lg border bg-card">
                                    <p className="text-xs text-muted-foreground mb-1">Stochastic</p>
                                    <div className="flex gap-4">
                                        <div>
                                            <span className="text-lg font-bold">%K: {data.stochastic.values[0].slowK.toFixed(1)}</span>
                                        </div>
                                        <div>
                                            <span className="text-lg font-bold">%D: {data.stochastic.values[0].slowD.toFixed(1)}</span>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* MACD */}
                            {data.macd?.values?.[0] && (
                                <div className="p-4 rounded-lg border bg-card col-span-2">
                                    <p className="text-xs text-muted-foreground mb-2">MACD</p>
                                    <div className="grid grid-cols-3 gap-4">
                                        <div>
                                            <span className="text-xs text-muted-foreground">MACD</span>
                                            <p className={`text-lg font-bold ${data.macd.values[0].macd >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                                {data.macd.values[0].macd.toFixed(2)}
                                            </p>
                                        </div>
                                        <div>
                                            <span className="text-xs text-muted-foreground">Signal</span>
                                            <p className="text-lg font-bold">{data.macd.values[0].signal.toFixed(2)}</p>
                                        </div>
                                        <div>
                                            <span className="text-xs text-muted-foreground">Histogram</span>
                                            <p className={`text-lg font-bold ${data.macd.values[0].histogram >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                                {data.macd.values[0].histogram.toFixed(2)}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </TabsContent>

                    <TabsContent value="trend" className="mt-4">
                        <div className="grid grid-cols-2 gap-4">
                            {data.sma20?.values?.[0] && (
                                <IndicatorCard label="SMA (20)" value={data.sma20.values[0].value} format="price" />
                            )}
                            {data.sma50?.values?.[0] && (
                                <IndicatorCard label="SMA (50)" value={data.sma50.values[0].value} format="price" />
                            )}
                            {data.ema12?.values?.[0] && (
                                <IndicatorCard label="EMA (12)" value={data.ema12.values[0].value} format="price" />
                            )}
                            {data.ema26?.values?.[0] && (
                                <IndicatorCard label="EMA (26)" value={data.ema26.values[0].value} format="price" />
                            )}
                            {data.adx?.values?.[0] && (
                                <IndicatorCard
                                    label="ADX (14)"
                                    value={data.adx.values[0].value}
                                    format="number"
                                    signal={getSignal('ADX', data.adx.values[0].value)}
                                />
                            )}
                        </div>
                    </TabsContent>

                    <TabsContent value="volatility" className="mt-4">
                        <div className="grid grid-cols-2 gap-4">
                            {data.atr?.values?.[0] && (
                                <IndicatorCard label="ATR (14)" value={data.atr.values[0].value} format="price" />
                            )}

                            {/* Bollinger Bands */}
                            {data.bollingerBands?.values?.[0] && (
                                <div className="p-4 rounded-lg border bg-card col-span-2">
                                    <p className="text-xs text-muted-foreground mb-2">Bandas de Bollinger</p>
                                    <div className="grid grid-cols-3 gap-4">
                                        <div>
                                            <span className="text-xs text-muted-foreground">Superior</span>
                                            <p className="text-lg font-bold text-red-500">
                                                ${data.bollingerBands.values[0].upper.toFixed(2)}
                                            </p>
                                        </div>
                                        <div>
                                            <span className="text-xs text-muted-foreground">Media</span>
                                            <p className="text-lg font-bold">
                                                ${data.bollingerBands.values[0].middle.toFixed(2)}
                                            </p>
                                        </div>
                                        <div>
                                            <span className="text-xs text-muted-foreground">Inferior</span>
                                            <p className="text-lg font-bold text-green-500">
                                                ${data.bollingerBands.values[0].lower.toFixed(2)}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </TabsContent>
                </Tabs>
            </CardContent>
        </Card>
    );
}

function IndicatorCard({
    label,
    value,
    format,
    signal,
}: {
    label: string;
    value: number;
    format: 'number' | 'price' | 'percent';
    signal?: { signal: 'buy' | 'sell' | 'neutral'; label: string };
}) {
    const formattedValue = format === 'price'
        ? `$${value.toFixed(2)}`
        : format === 'percent'
            ? `${value.toFixed(2)}%`
            : value.toFixed(2);

    return (
        <div className="p-4 rounded-lg border bg-card">
            <div className="flex items-center justify-between mb-1">
                <p className="text-xs text-muted-foreground">{label}</p>
                {signal && (
                    <Badge
                        variant={signal.signal === 'buy' ? 'default' : signal.signal === 'sell' ? 'destructive' : 'secondary'}
                        className={`text-xs ${signal.signal === 'buy'
                                ? 'bg-green-500/20 text-green-500'
                                : signal.signal === 'sell'
                                    ? 'bg-red-500/20 text-red-500'
                                    : ''
                            }`}
                    >
                        {signal.label}
                    </Badge>
                )}
            </div>
            <p className="text-xl font-bold">{formattedValue}</p>
        </div>
    );
}

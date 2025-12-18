'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { TrendingUp, TrendingDown, Building2, User, Calendar } from 'lucide-react';

type CongressTrade = {
    symbol: string;
    name: string;
    transactionDate: string;
    transactionType: 'buy' | 'sell' | 'exchange';
    amount: string;
    assetDescription: string;
    ownerType: string;
    congress: 'senate' | 'house';
};

interface CongressTradingPanelProps {
    symbol?: string;
}

export default function CongressTradingPanel({ symbol }: CongressTradingPanelProps) {
    const [trades, setTrades] = useState<CongressTrade[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchTrades() {
            setLoading(true);
            try {
                const { getCongressTrading } = await import('@/lib/actions/finnhub.actions');
                const data = await getCongressTrading(symbol);
                setTrades(data);
                setError(null);
            } catch (err) {
                console.error('Error fetching congress trading:', err);
                setError('Error al cargar datos de trading del congreso');
            } finally {
                setLoading(false);
            }
        }
        fetchTrades();
    }, [symbol]);

    if (loading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Building2 className="h-5 w-5" />
                        Trading del Congreso
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="space-y-3">
                        {[1, 2, 3].map((i) => (
                            <Skeleton key={i} className="h-16 w-full" />
                        ))}
                    </div>
                </CardContent>
            </Card>
        );
    }

    if (error) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Building2 className="h-5 w-5" />
                        Trading del Congreso
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-muted-foreground">{error}</p>
                </CardContent>
            </Card>
        );
    }

    if (trades.length === 0) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Building2 className="h-5 w-5" />
                        Trading del Congreso
                    </CardTitle>
                    <CardDescription>
                        Transacciones de senadores y congresistas
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <p className="text-muted-foreground text-center py-6">
                        No hay transacciones recientes del congreso {symbol ? `para ${symbol}` : ''}
                    </p>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Building2 className="h-5 w-5" />
                    Trading del Congreso
                </CardTitle>
                <CardDescription>
                    {trades.length} transacciones recientes de políticos
                </CardDescription>
            </CardHeader>
            <CardContent>
                <ScrollArea className="h-[400px] pr-4">
                    <div className="space-y-3">
                        {trades.map((trade, index) => (
                            <div
                                key={`${trade.symbol}-${trade.transactionDate}-${index}`}
                                className="flex items-start justify-between p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors"
                            >
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="font-semibold text-sm">{trade.symbol}</span>
                                        <Badge
                                            variant={trade.transactionType === 'buy' ? 'default' : 'destructive'}
                                            className={`text-xs ${trade.transactionType === 'buy'
                                                    ? 'bg-green-500/20 text-green-500 hover:bg-green-500/30'
                                                    : 'bg-red-500/20 text-red-500 hover:bg-red-500/30'
                                                }`}
                                        >
                                            {trade.transactionType === 'buy' ? (
                                                <TrendingUp className="h-3 w-3 mr-1" />
                                            ) : (
                                                <TrendingDown className="h-3 w-3 mr-1" />
                                            )}
                                            {trade.transactionType.toUpperCase()}
                                        </Badge>
                                        <Badge variant="outline" className="text-xs">
                                            {trade.congress === 'senate' ? 'Senado' : 'Cámara'}
                                        </Badge>
                                    </div>
                                    <p className="text-sm text-muted-foreground flex items-center gap-1">
                                        <User className="h-3 w-3" />
                                        {trade.name || 'Político'}
                                    </p>
                                    <p className="text-xs text-muted-foreground truncate mt-1">
                                        {trade.assetDescription || trade.symbol}
                                    </p>
                                </div>
                                <div className="text-right ml-3">
                                    <p className="font-medium text-sm">{trade.amount || 'N/A'}</p>
                                    <p className="text-xs text-muted-foreground flex items-center gap-1 justify-end">
                                        <Calendar className="h-3 w-3" />
                                        {new Date(trade.transactionDate).toLocaleDateString('es-ES', {
                                            day: '2-digit',
                                            month: 'short',
                                            year: 'numeric'
                                        })}
                                    </p>
                                </div>
                            </div>
                        ))}
                    </div>
                </ScrollArea>
            </CardContent>
        </Card>
    );
}

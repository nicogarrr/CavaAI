'use client';

import { useEffect, useState } from 'react';
import { getInsiderTrading, InsiderTrade } from '@/lib/actions/fmp.actions';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Users, TrendingUp, TrendingDown, Loader2 } from 'lucide-react';

interface InsiderTradingPanelProps {
    symbol: string;
}

export default function InsiderTradingPanel({ symbol }: InsiderTradingPanelProps) {
    const [trades, setTrades] = useState<InsiderTrade[]>([]);
    const [loading, setLoading] = useState(true);
    const [stats, setStats] = useState({ buys: 0, sells: 0, netValue: 0 });

    useEffect(() => {
        async function fetchData() {
            try {
                setLoading(true);
                const data = await getInsiderTrading(symbol, 30);
                const insiderTrades = data?.insiderTrades || [];
                setTrades(insiderTrades);

                // Calculate stats
                let buys = 0, sells = 0, netValue = 0;
                insiderTrades.forEach((t: InsiderTrade) => {
                    const value = t.securitiesTransacted * t.price;
                    if (t.typeOfTransaction?.toLowerCase().includes('buy') ||
                        t.typeOfTransaction?.toLowerCase().includes('purchase') ||
                        t.typeOfTransaction === 'P') {
                        buys++;
                        netValue += value;
                    } else if (t.typeOfTransaction?.toLowerCase().includes('sell') ||
                        t.typeOfTransaction?.toLowerCase().includes('sale') ||
                        t.typeOfTransaction === 'S') {
                        sells++;
                        netValue -= value;
                    }
                });
                setStats({ buys, sells, netValue });
            } catch (err) {
                console.error('Error fetching insider trading:', err);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, [symbol]);

    const formatCurrency = (num: number) => {
        if (Math.abs(num) >= 1e9) return `$${(num / 1e9).toFixed(2)}B`;
        if (Math.abs(num) >= 1e6) return `$${(num / 1e6).toFixed(2)}M`;
        if (Math.abs(num) >= 1e3) return `$${(num / 1e3).toFixed(2)}K`;
        return `$${num.toFixed(2)}`;
    };

    const formatDate = (dateStr: string) => {
        return new Date(dateStr).toLocaleDateString('es-ES', {
            day: '2-digit',
            month: 'short',
            year: 'numeric'
        });
    };

    if (loading) {
        return (
            <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader>
                    <CardTitle className="text-gray-100 flex items-center gap-2">
                        <Users className="h-5 w-5 text-teal-400" />
                        Insider Trading
                        <Loader2 className="h-4 w-4 animate-spin ml-auto text-gray-400" />
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                    <Skeleton className="h-20 w-full bg-gray-700" />
                    <Skeleton className="h-16 w-full bg-gray-700" />
                    <Skeleton className="h-16 w-full bg-gray-700" />
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="bg-gray-800/50 border-gray-700">
            <CardHeader>
                <CardTitle className="text-gray-100 flex items-center gap-2">
                    <Users className="h-5 w-5 text-teal-400" />
                    Insider Trading
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Summary Stats */}
                <div className="grid grid-cols-3 gap-3">
                    <div className="bg-green-900/30 border border-green-800/50 rounded-lg p-3 text-center">
                        <TrendingUp className="h-5 w-5 text-green-400 mx-auto mb-1" />
                        <p className="text-2xl font-bold text-green-400">{stats.buys}</p>
                        <p className="text-xs text-gray-400">Compras</p>
                    </div>
                    <div className="bg-red-900/30 border border-red-800/50 rounded-lg p-3 text-center">
                        <TrendingDown className="h-5 w-5 text-red-400 mx-auto mb-1" />
                        <p className="text-2xl font-bold text-red-400">{stats.sells}</p>
                        <p className="text-xs text-gray-400">Ventas</p>
                    </div>
                    <div className={`rounded-lg p-3 text-center border ${stats.netValue >= 0 ? 'bg-green-900/20 border-green-800/50' : 'bg-red-900/20 border-red-800/50'}`}>
                        <p className={`text-lg font-bold ${stats.netValue >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {formatCurrency(stats.netValue)}
                        </p>
                        <p className="text-xs text-gray-400">Valor Neto</p>
                    </div>
                </div>

                {/* Recent Trades */}
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                    <h4 className="text-sm font-semibold text-gray-400 uppercase">Últimas Transacciones</h4>
                    {trades.length === 0 ? (
                        <p className="text-sm text-gray-500 text-center py-4">
                            No hay datos de insider trading disponibles
                        </p>
                    ) : (
                        trades.slice(0, 10).map((trade, idx) => {
                            const isBuy = trade.typeOfTransaction?.toLowerCase().includes('buy') ||
                                trade.typeOfTransaction?.toLowerCase().includes('purchase') ||
                                trade.typeOfTransaction === 'P';
                            return (
                                <div key={idx} className="flex items-center justify-between p-3 bg-gray-900/50 rounded-lg border border-gray-700/50">
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium text-gray-100 truncate">
                                            {trade.reportingName}
                                        </p>
                                        {trade.reportingTitle && (
                                            <p className="text-xs text-gray-400 truncate">{trade.reportingTitle}</p>
                                        )}
                                        <p className="text-xs text-gray-500">{formatDate(trade.transactionDate)}</p>
                                    </div>
                                    <div className="text-right ml-3">
                                        <Badge className={isBuy ? 'bg-green-600' : 'bg-red-600'}>
                                            {isBuy ? 'Compra' : 'Venta'}
                                        </Badge>
                                        <p className="text-sm font-semibold text-gray-200 mt-1">
                                            {trade.securitiesTransacted?.toLocaleString()} acciones
                                        </p>
                                        <p className="text-xs text-gray-400">@ ${trade.price?.toFixed(2)}</p>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>
            </CardContent>
        </Card>
    );
}

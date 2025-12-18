'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Building, TrendingUp, TrendingDown, Minus, PieChart } from 'lucide-react';

type InstitutionalHolder = {
    name: string;
    share: number;
    change: number;
    filingDate: string;
    value: number;
};

type InstitutionalOwnership = {
    symbol: string;
    holders: InstitutionalHolder[];
    ownershipPercent: number;
};

interface InstitutionalHoldingsPanelProps {
    symbol: string;
}

function formatValue(value: number): string {
    if (value >= 1_000_000_000) {
        return `$${(value / 1_000_000_000).toFixed(2)}B`;
    }
    if (value >= 1_000_000) {
        return `$${(value / 1_000_000).toFixed(2)}M`;
    }
    if (value >= 1_000) {
        return `$${(value / 1_000).toFixed(2)}K`;
    }
    return `$${value.toFixed(2)}`;
}

function formatShares(shares: number): string {
    if (shares >= 1_000_000) {
        return `${(shares / 1_000_000).toFixed(2)}M`;
    }
    if (shares >= 1_000) {
        return `${(shares / 1_000).toFixed(2)}K`;
    }
    return shares.toString();
}

export default function InstitutionalHoldingsPanel({ symbol }: InstitutionalHoldingsPanelProps) {
    const [data, setData] = useState<InstitutionalOwnership | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchHoldings() {
            setLoading(true);
            try {
                const { getInstitutionalHoldings } = await import('@/lib/actions/finnhub.actions');
                const result = await getInstitutionalHoldings(symbol);
                setData(result);
                setError(null);
            } catch (err) {
                console.error('Error fetching institutional holdings:', err);
                setError('Error al cargar datos de propiedad institucional');
            } finally {
                setLoading(false);
            }
        }
        fetchHoldings();
    }, [symbol]);

    if (loading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Building className="h-5 w-5" />
                        Propiedad Institucional
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="space-y-3">
                        {[1, 2, 3, 4, 5].map((i) => (
                            <Skeleton key={i} className="h-12 w-full" />
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
                        <Building className="h-5 w-5" />
                        Propiedad Institucional
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-muted-foreground text-center py-6">
                        {error || `No hay datos de propiedad institucional para ${symbol}`}
                    </p>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Building className="h-5 w-5" />
                    Propiedad Institucional (13F)
                </CardTitle>
                <CardDescription className="flex items-center gap-4">
                    <span className="flex items-center gap-1">
                        <PieChart className="h-4 w-4" />
                        {data.ownershipPercent.toFixed(1)}% institucional
                    </span>
                    <span>{data.holders.length} principales tenedores</span>
                </CardDescription>
            </CardHeader>
            <CardContent>
                <ScrollArea className="h-[350px] pr-4">
                    <div className="space-y-2">
                        {data.holders.map((holder, index) => (
                            <div
                                key={`${holder.name}-${index}`}
                                className="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors"
                            >
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <Badge variant="outline" className="text-xs">
                                            #{index + 1}
                                        </Badge>
                                        <span className="font-medium text-sm truncate">
                                            {holder.name}
                                        </span>
                                    </div>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        {formatShares(holder.share)} acciones
                                    </p>
                                </div>
                                <div className="text-right ml-3">
                                    <p className="font-medium text-sm">{formatValue(holder.value)}</p>
                                    <div className="flex items-center justify-end gap-1 mt-1">
                                        {holder.change > 0 ? (
                                            <>
                                                <TrendingUp className="h-3 w-3 text-green-500" />
                                                <span className="text-xs text-green-500">
                                                    +{formatShares(holder.change)}
                                                </span>
                                            </>
                                        ) : holder.change < 0 ? (
                                            <>
                                                <TrendingDown className="h-3 w-3 text-red-500" />
                                                <span className="text-xs text-red-500">
                                                    {formatShares(holder.change)}
                                                </span>
                                            </>
                                        ) : (
                                            <>
                                                <Minus className="h-3 w-3 text-muted-foreground" />
                                                <span className="text-xs text-muted-foreground">
                                                    Sin cambio
                                                </span>
                                            </>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </ScrollArea>
            </CardContent>
        </Card>
    );
}

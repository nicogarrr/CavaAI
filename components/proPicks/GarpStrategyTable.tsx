'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';
import { Loader2, TrendingUp, Info, ExternalLink, RefreshCw } from 'lucide-react';
import { getGarpStrategy, type GarpStock } from '@/lib/actions/fmp.actions';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export default function GarpStrategyTable() {
    const [stocks, setStocks] = useState<GarpStock[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchData = async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await getGarpStrategy(20);
            if (result && result.data) {
                setStocks(result.data);
            } else {
                setStocks([]);
            }
        } catch (err) {
            console.error(err);
            setError("Error al cargar la estrategia. Intenta nuevamente.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h2 className="text-xl font-semibold text-gray-100 flex items-center gap-2">
                        Top 12 Meses (Estrategia GARP)
                        <Badge variant="outline" className="text-blue-400 border-blue-400">
                            Algoritmo
                        </Badge>
                    </h2>
                    <p className="text-sm text-gray-400 mt-1">
                        Growth At A Reasonable Price: Calidad (ROE &gt; 12%) + Tendencia (Precio &gt; Media 200) + Valor (PEG &lt; 2.25)
                    </p>
                </div>
                <Button
                    onClick={fetchData}
                    disabled={loading}
                    variant="outline"
                    className="border-gray-700 text-gray-300 hover:text-white"
                >
                    {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <RefreshCw className="h-4 w-4 mr-2" />}
                    Actualizar
                </Button>
            </div>

            {error && (
                <Card className="p-4 border-red-800 bg-red-900/10 text-red-400">
                    {error}
                </Card>
            )}

            {!loading && !error && stocks.length === 0 && (
                <Card className="p-8 border-dashed border-gray-700 bg-gray-900/30 text-center">
                    <Info className="h-10 w-10 text-gray-500 mx-auto mb-3" />
                    <p className="text-gray-300 font-medium">No hay resultados exactos hoy</p>
                    <p className="text-sm text-gray-500 max-w-md mx-auto mt-2">
                        El mercado está exigente. Ninguna empresa del S&P 500 cumple simultáneamente las 3 reglas de oro (ROE &gt; 12%, Uptrend, PEG &lt; 2.25) en este momento.
                    </p>
                </Card>
            )}

            {!loading && stocks.length > 0 && (
                <Card className="border-gray-800 bg-gray-900/50 overflow-hidden">
                    <div className="overflow-x-auto">
                        <Table>
                            <TableHeader className="bg-gray-800/50">
                                <TableRow className="border-gray-700 hover:bg-transparent">
                                    <TableHead className="text-gray-400">Empresa</TableHead>
                                    <TableHead className="text-right text-gray-400">Precio</TableHead>
                                    <TableHead className="text-right text-gray-400">
                                        <TooltipProvider>
                                            <Tooltip>
                                                <TooltipTrigger className="flex items-center gap-1 justify-end cursor-help">
                                                    ROE (Calidad)
                                                    <Info className="h-3 w-3" />
                                                </TooltipTrigger>
                                                <TooltipContent className="bg-gray-800 border-gray-700 text-gray-200">
                                                    Return on Equity. Buscamos &gt; 12%
                                                </TooltipContent>
                                            </Tooltip>
                                        </TooltipProvider>
                                    </TableHead>
                                    <TableHead className="text-right text-gray-400">
                                        <TooltipProvider>
                                            <Tooltip>
                                                <TooltipTrigger className="flex items-center gap-1 justify-end cursor-help">
                                                    Tendencia
                                                    <TrendingUp className="h-3 w-3" />
                                                </TooltipTrigger>
                                                <TooltipContent className="bg-gray-800 border-gray-700 text-gray-200">
                                                    Precio vs Media Móvil 200 días.
                                                </TooltipContent>
                                            </Tooltip>
                                        </TooltipProvider>
                                    </TableHead>
                                    <TableHead className="text-right text-gray-400">
                                        <TooltipProvider>
                                            <Tooltip>
                                                <TooltipTrigger className="flex items-center gap-1 justify-end cursor-help">
                                                    PEG (Valor)
                                                    <Info className="h-3 w-3" />
                                                </TooltipTrigger>
                                                <TooltipContent className="bg-gray-800 border-gray-700 text-gray-200">
                                                    Price/Earnings to Growth. Buscamos &lt; 2.25
                                                </TooltipContent>
                                            </Tooltip>
                                        </TooltipProvider>
                                    </TableHead>
                                    <TableHead className="text-right text-gray-400">Acción</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {stocks.map((stock) => (
                                    <TableRow key={stock.symbol} className="border-gray-800 hover:bg-gray-800/50 transition-colors">
                                        <TableCell>
                                            <div className="flex flex-col">
                                                <span className="font-bold text-gray-200 text-base">{stock.symbol}</span>
                                                <span className="text-xs text-gray-500 line-clamp-1">{stock.companyName}</span>
                                                <span className="text-xs text-blue-400/70 mt-0.5">{stock.sector}</span>
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-right font-mono text-gray-300">
                                            ${stock.price.toFixed(2)}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20 font-mono">
                                                {stock.doe.toFixed(1)}%
                                            </Badge>
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <div className={`flex items-center justify-end gap-1 text-sm ${stock.price > stock.sma200 ? 'text-green-400' : 'text-red-400'}`}>
                                                {stock.price > stock.sma200 ? (
                                                    <>
                                                        <TrendingUp className="h-3 w-3" />
                                                        Alcista
                                                    </>
                                                ) : 'Bajista'}
                                            </div>
                                            <div className="text-xs text-gray-600 font-mono mt-1">
                                                SMA200: ${stock.sma200.toFixed(0)}
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <Badge variant="outline" className={`font-mono border-0 ${stock.peg < 1.0 ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'
                                                }`}>
                                                {stock.peg.toFixed(2)}x
                                            </Badge>
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <Link href={`/stocks/${stock.symbol}`}>
                                                <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-gray-400 hover:text-white">
                                                    <ExternalLink className="h-4 w-4" />
                                                </Button>
                                            </Link>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                </Card>
            )}
        </div>
    );
}

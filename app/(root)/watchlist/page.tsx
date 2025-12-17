import { getWatchlist } from '@/lib/actions/watchlist.actions';
import { getStockFinancialData } from '@/lib/actions/finnhub.actions';
import { getValuationData } from '@/lib/actions/fmp.actions';
import { Eye, TrendingUp, TrendingDown, ArrowRight, Trash2, AlertCircle } from 'lucide-react';
import Link from 'next/link';
import WatchlistRemoveButton from '@/components/watchlist/WatchlistRemoveButton';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";

export const dynamic = 'force-dynamic';
export const revalidate = 0;

interface WatchlistStock {
    symbol: string;
    name: string;
    price: number;
    change: number;
    changePercent: number;
    marketCap: number | null;
    peRatio: number | null;
    dcfValue: number | null;
    dcfUpside: number | null;
    addedAt: Date;
}

export default async function WatchlistPage() {
    const watchlistItems = await getWatchlist();

    // Obtener datos de cada acción
    const watchlistStocks: WatchlistStock[] = await Promise.all(
        watchlistItems.map(async (item) => {
            try {
                // Fetch Financial Data and Valuation Data in parallel
                const [financialData, valuationData] = await Promise.all([
                    getStockFinancialData(item.symbol),
                    getValuationData(item.symbol)
                ]);

                // Extract Valuation Metrics
                const ratios = valuationData.ratios?.ratios?.[0];
                const dcf = valuationData.dcf?.dcf?.[0];
                const ev = valuationData.ev?.enterpriseValue?.[0];

                const currentPrice = financialData?.quote?.c || 0;
                const intrinsicValue = dcf?.dcf || 0;
                const dcfUpside = (currentPrice > 0 && intrinsicValue > 0)
                    ? ((intrinsicValue - currentPrice) / currentPrice) * 100
                    : null;

                return {
                    symbol: item.symbol,
                    name: financialData?.profile?.name || item.symbol,
                    price: currentPrice,
                    change: financialData?.quote?.d || 0,
                    changePercent: financialData?.quote?.dp || 0,
                    marketCap: ev?.marketCapitalization || null,
                    peRatio: ratios?.peRatioTTM || null,
                    dcfValue: intrinsicValue || null,
                    dcfUpside: dcfUpside,
                    addedAt: item.addedAt
                };
            } catch {
                return {
                    symbol: item.symbol,
                    name: item.symbol,
                    price: 0,
                    change: 0,
                    changePercent: 0,
                    marketCap: null,
                    peRatio: null,
                    dcfValue: null,
                    dcfUpside: null,
                    addedAt: item.addedAt
                };
            }
        })
    );

    const formatNumber = (num: number | null) => {
        if (num === null || num === undefined) return '-';
        return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };

    const formatBillions = (num: number | null) => {
        if (!num) return '-';
        if (num >= 1e12) return `$${(num / 1e12).toFixed(2)}T`;
        if (num >= 1e9) return `$${(num / 1e9).toFixed(2)}B`;
        if (num >= 1e6) return `$${(num / 1e6).toFixed(2)}M`;
        return `$${num.toLocaleString()}`;
    };

    return (
        <div className="flex min-h-screen flex-col p-6 space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-gray-100 flex items-center gap-3">
                        <Eye className="h-8 w-8 text-purple-400" />
                        Watchlist
                    </h1>
                    <p className="text-gray-400 mt-1">
                        Seguimiento detallado de valoración y métricas
                    </p>
                </div>
            </div>

            {watchlistStocks.length === 0 ? (
                <Card className="bg-gray-800/50 border-gray-700">
                    <CardContent className="flex flex-col items-center justify-center py-16 text-center">
                        <Eye className="h-16 w-16 text-gray-600 mb-4" />
                        <h2 className="text-xl font-semibold text-gray-300 mb-2">Tu Watchlist está vacía</h2>
                        <p className="text-gray-500 mb-6 max-w-md">
                            Busca acciones y haz click en "Añadir a Watchlist" para monitorizarlas aquí.
                        </p>
                        <Link href="/" className="text-teal-400 hover:text-teal-300">
                            ← Ir a buscar acciones
                        </Link>
                    </CardContent>
                </Card>
            ) : (
                <div className="rounded-lg border border-gray-700 bg-gray-900/50 overflow-hidden">
                    <Table>
                        <TableHeader className="bg-gray-800/80">
                            <TableRow className="hover:bg-gray-800/80 border-gray-700">
                                <TableHead className="text-gray-300">Símbolo</TableHead>
                                <TableHead className="text-right text-gray-300">Precio</TableHead>
                                <TableHead className="text-right text-gray-300">Cambio 24h</TableHead>
                                <TableHead className="text-right text-gray-300">Market Cap</TableHead>
                                <TableHead className="text-right text-gray-300">PER (TTM)</TableHead>
                                <TableHead className="text-right text-gray-300">DCF (Intrínseco)</TableHead>
                                <TableHead className="text-right text-gray-300">Upside DCF</TableHead>
                                <TableHead className="text-right text-gray-300">Acciones</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {watchlistStocks.map((stock) => (
                                <TableRow key={stock.symbol} className="hover:bg-gray-800/30 border-gray-800 transition-colors">
                                    <TableCell>
                                        <Link href={`/stocks/${stock.symbol}`} className="flex items-center gap-3 group">
                                            <div className="w-10 h-10 rounded-lg bg-gray-800 flex items-center justify-center font-bold text-gray-300 group-hover:bg-gray-700 transition-colors">
                                                {stock.symbol.slice(0, 2)}
                                            </div>
                                            <div>
                                                <div className="font-bold text-gray-200 group-hover:text-blue-400 transition-colors">
                                                    {stock.symbol}
                                                </div>
                                                <div className="text-xs text-gray-500 max-w-[150px] truncate">
                                                    {stock.name}
                                                </div>
                                            </div>
                                        </Link>
                                    </TableCell>
                                    <TableCell className="text-right font-mono font-medium text-gray-200">
                                        ${formatNumber(stock.price)}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <div className={`flex items-center justify-end gap-1 ${stock.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {stock.changePercent >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                                            <span className="font-mono">
                                                {stock.changePercent >= 0 ? '+' : ''}{stock.changePercent.toFixed(2)}%
                                            </span>
                                        </div>
                                    </TableCell>
                                    <TableCell className="text-right text-gray-400 font-mono">
                                        {formatBillions(stock.marketCap)}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        {stock.peRatio ? (
                                            <Badge variant="outline" className={`font-mono border-gray-700 ${stock.peRatio < 15 ? 'text-green-400' :
                                                stock.peRatio < 25 ? 'text-yellow-400' : 'text-red-400'
                                                }`}>
                                                {stock.peRatio.toFixed(1)}x
                                            </Badge>
                                        ) : (
                                            <span className="text-gray-600">-</span>
                                        )}
                                    </TableCell>
                                    <TableCell className="text-right font-mono text-gray-300">
                                        {stock.dcfValue ? `$${formatNumber(stock.dcfValue)}` : '-'}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        {stock.dcfUpside !== null ? (
                                            <Badge variant="outline" className={`font-mono border-gray-700 ${stock.dcfUpside > 20 ? 'text-green-400 bg-green-900/10' :
                                                stock.dcfUpside > 0 ? 'text-green-300' : 'text-red-400'
                                                }`}>
                                                {stock.dcfUpside > 0 ? '+' : ''}{stock.dcfUpside.toFixed(1)}%
                                            </Badge>
                                        ) : (
                                            <span className="text-gray-600">-</span>
                                        )}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <div className="flex items-center justify-end gap-2">
                                            <WatchlistRemoveButton symbol={stock.symbol} />
                                            <Link
                                                href={`/stocks/${stock.symbol}`}
                                                className="p-2 hover:bg-gray-700 rounded-lg transition-colors text-gray-400 hover:text-white"
                                            >
                                                <ArrowRight className="w-4 h-4" />
                                            </Link>
                                        </div>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            )}
        </div>
    );
}

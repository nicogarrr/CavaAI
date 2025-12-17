import { getWatchlist } from '@/lib/actions/watchlist.actions';
import { getStockFinancialData } from '@/lib/actions/finnhub.actions';
import { Eye, TrendingUp, TrendingDown, ArrowRight } from 'lucide-react';
import Link from 'next/link';
import WatchlistRemoveButton from '@/components/watchlist/WatchlistRemoveButton';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

interface WatchlistStock {
    symbol: string;
    name: string;
    price: number;
    change: number;
    changePercent: number;
    addedAt: Date;
}

export default async function WatchlistPage() {
    const watchlistItems = await getWatchlist();

    // Obtener datos de cada acción
    const watchlistStocks: WatchlistStock[] = await Promise.all(
        watchlistItems.map(async (item) => {
            try {
                const financialData = await getStockFinancialData(item.symbol);

                return {
                    symbol: item.symbol,
                    name: financialData?.profile?.name || item.symbol,
                    price: financialData?.quote?.c || 0,
                    change: financialData?.quote?.d || 0,
                    changePercent: financialData?.quote?.dp || 0,
                    addedAt: item.addedAt
                };
            } catch {
                return {
                    symbol: item.symbol,
                    name: item.symbol,
                    price: 0,
                    change: 0,
                    changePercent: 0,
                    addedAt: item.addedAt
                };
            }
        })
    );

    return (
        <div className="flex min-h-screen flex-col p-6">
            <div className="mb-8">
                <div className="flex items-center gap-3 mb-4">
                    <Eye className="h-8 w-8 text-purple-400" />
                    <div>
                        <h1 className="text-3xl font-bold text-gray-100">Watchlist</h1>
                        <p className="text-gray-400 mt-1">
                            Acciones que estás siguiendo
                        </p>
                    </div>
                </div>
            </div>

            {watchlistStocks.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                    <Eye className="h-16 w-16 text-gray-600 mb-4" />
                    <h2 className="text-xl font-semibold text-gray-300 mb-2">Tu Watchlist está vacía</h2>
                    <p className="text-gray-500 mb-6 max-w-md">
                        Busca acciones y haz click en "Añadir a Watchlist" para seguirlas aquí
                    </p>
                    <Link href="/" className="text-teal-400 hover:text-teal-300">
                        ← Ir a buscar acciones
                    </Link>
                </div>
            ) : (
                <div className="grid gap-4">
                    {watchlistStocks.map((stock) => (
                        <div
                            key={stock.symbol}
                            className="flex items-center justify-between p-4 bg-gray-800/50 border border-gray-700 rounded-lg hover:bg-gray-800 transition-colors"
                        >
                            <Link
                                href={`/stocks/${stock.symbol}`}
                                className="flex items-center gap-4 flex-1"
                            >
                                <div className="w-12 h-12 rounded-full bg-gray-700 flex items-center justify-center">
                                    <span className="text-lg font-bold text-gray-300">
                                        {stock.symbol.slice(0, 2)}
                                    </span>
                                </div>
                                <div>
                                    <div className="flex items-center gap-2">
                                        <span className="text-lg font-semibold text-white">{stock.symbol}</span>
                                        {stock.changePercent >= 0 ? (
                                            <TrendingUp className="w-4 h-4 text-green-400" />
                                        ) : (
                                            <TrendingDown className="w-4 h-4 text-red-400" />
                                        )}
                                    </div>
                                    <span className="text-sm text-gray-400">{stock.name}</span>
                                </div>
                            </Link>

                            <div className="flex items-center gap-6">
                                <div className="text-right">
                                    <div className="text-lg font-semibold text-white">
                                        ${stock.price.toFixed(2)}
                                    </div>
                                    <div className={`text-sm ${stock.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                        {stock.changePercent >= 0 ? '+' : ''}{stock.changePercent.toFixed(2)}%
                                    </div>
                                </div>

                                <WatchlistRemoveButton symbol={stock.symbol} />

                                <Link
                                    href={`/stocks/${stock.symbol}`}
                                    className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                                >
                                    <ArrowRight className="w-5 h-5 text-gray-400" />
                                </Link>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

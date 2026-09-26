import { formatCompact, formatNumber, formatPercent, formatPrice, NA } from '@/lib/format';
import { getWatchlist } from '@/lib/actions/watchlist.actions';
import { getStockFinancialData } from '@/lib/actions/finnhub.actions';
import { Eye, TrendingUp, TrendingDown, ArrowRight } from 'lucide-react';
import Link from 'next/link';
import WatchlistRemoveButton from '@/components/watchlist/WatchlistRemoveButton';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCaption,
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
    price: number | null;
    change: number | null;
    changePercent: number | null;
    marketCap: number | null;
    peRatio: number | null;
    addedAt: Date;
}

export default async function WatchlistPage() {
    const watchlistItems = await getWatchlist();

    // Obtener datos de cada acción
    const watchlistStocks: WatchlistStock[] = await Promise.all(
        watchlistItems.map(async (item) => {
            try {
                // Fetch Financial Data (Finnhub)
                const financialData = await getStockFinancialData(item.symbol);

                // Extract metrics (Finnhub stock/metric)
                const metrics = financialData?.metrics?.metric ?? {};
                const marketCapM = typeof metrics.marketCapitalization === 'number' ? metrics.marketCapitalization : null;
                // peRatio puede venir ausente/null: se guarda null y se pinta NA ('N/D'), nunca se interpola sin guarda.
                const peRatio = typeof metrics.peTTM === 'number' && Number.isFinite(metrics.peTTM) ? metrics.peTTM : null;

                // Sin cotización válida no hay precio: null (no 0, que se confundiría con un precio real).
                const rawPrice = financialData?.quote?.c;
                const currentPrice = typeof rawPrice === 'number' && Number.isFinite(rawPrice) && rawPrice > 0 ? rawPrice : null;
                const rawChange = financialData?.quote?.d;
                const rawChangePercent = financialData?.quote?.dp;

                return {
                    symbol: item.symbol,
                    name: financialData?.profile?.name || item.symbol,
                    price: currentPrice,
                    change: currentPrice === null ? null : (typeof rawChange === 'number' && Number.isFinite(rawChange) ? rawChange : null),
                    changePercent: currentPrice === null ? null : (typeof rawChangePercent === 'number' && Number.isFinite(rawChangePercent) ? rawChangePercent : null),
                    marketCap: marketCapM !== null ? marketCapM * 1e6 : null, // Finnhub devuelve M USD
                    peRatio,
                    addedAt: item.addedAt
                };
            } catch {
                // Fallo de red/proveedor: todo a null para pintar NA ('N/D') + badge «sin datos».
                return {
                    symbol: item.symbol,
                    name: item.symbol,
                    price: null,
                    change: null,
                    changePercent: null,
                    marketCap: null,
                    peRatio: null,
                    addedAt: item.addedAt
                };
            }
        })
    );

    // Sin datos al final: las filas sin precio quedan excluidas de cualquier ordenación por métricas.
    const sortedStocks = [...watchlistStocks].sort((a, b) => Number(a.price === null) - Number(b.price === null));

    // Un único formateador para móvil y desktop: sin dato -> NA ('N/D'),
    // nunca un número interpolado sin guarda.
    const formatPeRatio = (peRatio: number | null) => {
        if (peRatio === null || peRatio === undefined || !Number.isFinite(peRatio)) return NA;
        return `${formatNumber(peRatio, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}x`;
    };

    const formatChangePercent = (changePercent: number | null) => {
        if (changePercent === null || changePercent === undefined || !Number.isFinite(changePercent)) return NA;
        // Finnhub ya manda puntos porcentuales (dp), no ratio.
        return formatPercent(changePercent, { fromRatio: false, digits: 2, signDisplay: 'always' });
    };

    const formatPriceCell = (price: number | null) => (price === null ? NA : formatPrice(price, 'USD'));

    return (
        <main id="content" tabIndex={-1} className="mx-auto flex w-full max-w-full min-w-0 flex-col space-y-6 overflow-x-clip p-4 sm:p-6">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                    <h1 className="flex items-center gap-2 text-2xl font-bold break-words text-gray-100 sm:gap-3 sm:text-3xl">
                        <Eye className="h-7 w-7 shrink-0 text-purple-400 sm:h-8 sm:w-8" aria-hidden="true" />
                        Watchlist
                    </h1>
                    <p className="mt-1 text-sm text-gray-400 sm:text-base">
                        Seguimiento detallado de valoración y métricas
                    </p>
                </div>
            </div>

            {watchlistStocks.length === 0 ? (
                <Card className="border-gray-700 bg-gray-800/50">
                    <CardContent className="flex flex-col items-center justify-center px-4 py-12 text-center sm:py-16">
                        <Eye className="mb-4 h-12 w-12 text-gray-600 sm:h-16 sm:w-16" aria-hidden="true" />
                        <h2 className="mb-2 text-lg font-semibold text-gray-300 sm:text-xl">Tu Watchlist está vacía</h2>
                        <p className="mb-6 max-w-md text-sm text-gray-500 sm:text-base">
                            Busca acciones y haz click en &ldquo;Añadir a Watchlist&rdquo; para monitorizarlas aquí.
                        </p>
                        <Link
                            href="/"
                            className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-teal-400/20 px-5 text-sm text-teal-400 transition-colors hover:text-teal-300"
                        >
                            ← Ir a buscar acciones
                        </Link>
                    </CardContent>
                </Card>
            ) : (
                <>
                    {/* Móvil (<md): cards apiladas con acciones táctiles ≥44px */}
                    <div className="space-y-3 md:hidden">
                        {sortedStocks.map((stock) => (
                            <article key={stock.symbol} className="min-w-0 rounded-xl border border-gray-700/60 bg-gray-900/60 p-4">
                                <div className="flex min-w-0 items-center gap-3">
                                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-gray-800 text-sm font-bold text-gray-300" aria-hidden="true">
                                        {stock.symbol.slice(0, 2)}
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <Link
                                            href={`/research/${stock.symbol}`}
                                            prefetch
                                            className="block truncate text-base font-bold text-gray-200"
                                        >
                                            {stock.symbol}
                                        </Link>
                                        <p className="truncate text-xs text-gray-500" title={stock.name}>
                                            {stock.name}
                                        </p>
                                        {stock.price === null ? (
                                            <Badge variant="outline" className="mt-1 border-gray-700 text-gray-400">
                                                sin datos
                                            </Badge>
                                        ) : null}
                                    </div>
                                    <div className={`flex shrink-0 items-center gap-1 font-mono text-sm ${stock.changePercent === null ? 'text-gray-500' : stock.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                        {stock.changePercent === null ? null : stock.changePercent >= 0 ? <TrendingUp className="h-4 w-4" aria-hidden="true" /> : <TrendingDown className="h-4 w-4" aria-hidden="true" />}
                                        <span>
                                            {formatChangePercent(stock.changePercent)}
                                        </span>
                                    </div>
                                </div>
                                <dl className="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-gray-800/50 px-2 py-3 text-center">
                                    <div className="min-w-0">
                                        <dt className="text-[11px] text-gray-500">Precio</dt>
                                        <dd className="truncate font-mono text-sm font-medium text-gray-200">{formatPriceCell(stock.price)}</dd>
                                    </div>
                                    <div className="min-w-0">
                                        <dt className="text-[11px] text-gray-500">Market Cap</dt>
                                        <dd className="truncate font-mono text-sm text-gray-400">
                                            {formatCompact(stock.marketCap, { maximumFractionDigits: 2 })}
                                        </dd>
                                    </div>
                                    <div className="min-w-0">
                                        <dt className="text-[11px] text-gray-500">PER (TTM)</dt>
                                        <dd className="truncate font-mono text-sm text-gray-300">{formatPeRatio(stock.peRatio)}</dd>
                                    </div>
                                </dl>
                                <div className="mt-3 flex items-center gap-2">
                                    <Link
                                        href={`/research/${stock.symbol}`}
                                        prefetch
                                        aria-label={`Ver análisis de ${stock.symbol}`}
                                        className="inline-flex min-h-[44px] flex-1 items-center justify-center gap-1.5 rounded-lg bg-gray-800 px-4 text-sm font-medium text-gray-200 transition-colors hover:bg-gray-700 hover:text-white"
                                    >
                                        Ver análisis
                                        <ArrowRight className="h-4 w-4" aria-hidden="true" />
                                    </Link>
                                    <WatchlistRemoveButton symbol={stock.symbol} />
                                </div>
                            </article>
                        ))}
                    </div>

                    {/* Desktop (≥md): tabla completa */}
                    <div className="hidden overflow-hidden rounded-lg border border-gray-700 bg-gray-900/50 md:block">
                        <Table regionLabel="Watchlist: precio, cambio, market cap y PER">
                            <TableCaption className="sr-only">Valoración y métricas de cada símbolo de tu watchlist: precio, cambio de sesión, market cap y PER</TableCaption>
                            <TableHeader className="bg-gray-800/80">
                                <TableRow className="border-gray-700 hover:bg-gray-800/80">
                                    <TableHead className="text-gray-300">Símbolo</TableHead>
                                    <TableHead className="text-right text-gray-300">Precio</TableHead>
                                    <TableHead className="text-right text-gray-300">Cambio sesión</TableHead>
                                    <TableHead className="text-right text-gray-300">Market Cap</TableHead>
                                    <TableHead className="text-right text-gray-300">PER (TTM)</TableHead>
                                    <TableHead className="text-right text-gray-300">Acciones</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {sortedStocks.map((stock) => (
                                    <TableRow key={stock.symbol} className="border-gray-800 transition-colors hover:bg-gray-800/30">
                                        <TableCell>
                                            <Link href={`/research/${stock.symbol}`} prefetch className="group flex items-center gap-3">
                                                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-800 font-bold text-gray-300 transition-colors group-hover:bg-gray-700">
                                                    {stock.symbol.slice(0, 2)}
                                                </div>
                                                <div>
                                                    <div className="flex items-center gap-2 font-bold text-gray-200 transition-colors group-hover:text-blue-400">
                                                        {stock.symbol}
                                                        {stock.price === null ? (
                                                            <Badge variant="outline" className="border-gray-700 font-normal text-gray-400">
                                                                sin datos
                                                            </Badge>
                                                        ) : null}
                                                    </div>
                                                    <div className="max-w-[150px] truncate text-xs text-gray-500" title={stock.name}>
                                                        {stock.name}
                                                    </div>
                                                </div>
                                            </Link>
                                        </TableCell>
                                        <TableCell className="text-right font-mono font-medium text-gray-200">
                                            {formatPriceCell(stock.price)}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            {stock.changePercent === null ? (
                                                <span className="font-mono text-gray-500">{NA}</span>
                                            ) : (
                                                <div className={`flex items-center justify-end gap-1 ${stock.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                    {stock.changePercent >= 0 ? <TrendingUp aria-hidden="true" className="h-3 w-3" /> : <TrendingDown aria-hidden="true" className="h-3 w-3" />}
                                                    <span className="font-mono">
                                                        {formatChangePercent(stock.changePercent)}
                                                    </span>
                                                </div>
                                            )}
                                        </TableCell>
                                        <TableCell className="text-right font-mono text-gray-400">
                                            {formatCompact(stock.marketCap, { maximumFractionDigits: 2 })}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            {stock.peRatio !== null && stock.peRatio !== undefined && Number.isFinite(stock.peRatio) ? (
                                                <Badge variant="outline" className={`border-gray-700 font-mono ${stock.peRatio < 15 ? 'text-green-400' :
                                                    stock.peRatio < 25 ? 'text-yellow-400' : 'text-red-400'
                                                    }`}>
                                                    {formatPeRatio(stock.peRatio)}
                                                </Badge>
                                            ) : (
                                                <span className="text-gray-500">{NA}</span>
                                            )}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <div className="flex items-center justify-end gap-2">
                                                <WatchlistRemoveButton symbol={stock.symbol} />
                                                <Link
                                                    href={`/research/${stock.symbol}`}
                                                    prefetch
                                                    className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-700 hover:text-white"
                                                    aria-label={`Ver ${stock.symbol}`}
                                                >
                                                    <ArrowRight aria-hidden="true" className="h-4 w-4" />
                                                </Link>
                                            </div>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                </>
            )}
        </main>
    );
}


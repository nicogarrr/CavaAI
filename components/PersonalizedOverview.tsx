'use client';

import { formatMoney, formatNumber, formatPercent } from '@/lib/format';
import { memo, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { StockCardSkeleton } from '@/components/LoadingState';
import { TrendingUp, TrendingDown, Wallet, ArrowRight, Eye, Newspaper, Brain, Gem } from 'lucide-react';
import { getPortfolioSummary, type PortfolioSummary } from '@/lib/actions/portfolio.actions';
import { getWatchlist } from '@/lib/actions/watchlist.actions';
import { getMarketIndices } from '@/lib/actions/market.actions';
import { getCompanyNews, getStockFinancialData, getStockQuote, getNews } from '@/lib/actions/finnhub.actions';
import { getScreenerStocksReal, getFairValue } from '@/lib/actions/screener.actions';


interface PersonalizedOverviewProps {
    userId: string;
}

interface WatchlistItem {
    symbol: string;
    name: string;
    price: number;
    changePercent: number;
}

interface MarketIndex {
    symbol: string;
    name: string;
    price: number;
    change: number;
    changePercent: number;
}

interface UndervaluedStock {
    symbol: string;
    name: string;
    price: number;
    fairValue: number;
    upside: number;
}

type NewsArticle = {
    headline?: string;
    url?: string;
    source?: string;
    datetime?: number;
    [key: string]: unknown;
};

// Tarjeta memorizada: la parrilla de índices re-renderiza con cada
// actualización del dashboard; memo evita reconciliar tarjetas sin cambios.
const MarketIndexCard = memo(function MarketIndexCard({ index }: { index: MarketIndex }) {
    return (
        <Card className="bg-gray-800/40 border-gray-700/50 hover:bg-gray-800/60 transition-colors">
            <CardContent className="p-4 flex items-center justify-between">
                <div>
                    <p className="text-sm text-gray-400 font-medium">{index.name}</p>
                    <p className="text-xl font-bold text-white mt-1">{formatMoney(index.price)}</p>
                </div>
                <div className={`text-right ${index.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    <div className="flex items-center justify-end gap-1">
                        {index.changePercent >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                        <span className="font-bold">{formatPercent(index.changePercent, { fromRatio: false, digits: 2, signDisplay: 'always' })}</span>
                    </div>
                    <p className="text-xs mt-1">{formatNumber(index.change, { signDisplay: 'always' })}</p>
                </div>
            </CardContent>
        </Card>
    );
});



function sectionError(error: unknown): string {
    if (error instanceof Error && error.message) {
        const message = error.message.replace(/https?:\/\/\S+/g, 'el servicio');
        return `${message}. Reintenta en unos segundos.`;
    }
    return 'No se pudieron cargar los datos. Reintenta en unos segundos.';
}

function InlineSectionError({ message, onRetry }: { message: string; onRetry: () => void }) {
    return (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-900/60 bg-amber-950/20 p-3 text-sm text-amber-200" role="status">
            <span>{message}</span>
            <button type="button" onClick={onRetry} className="underline hover:text-amber-100">Reintentar</button>
        </div>
    );
}

export default function PersonalizedOverview({ userId }: PersonalizedOverviewProps) {
    const [reloadToken, setReloadToken] = useState(0);
    const [portfolioSummary, setPortfolioSummary] = useState<PortfolioSummary | null>(null);
    const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
    const [news, setNews] = useState<NewsArticle[]>([]);
    // Noticias company-specific solo si hay simbolos seguidos; sin ellos la
    // tarjeta duplicaba a NewsSection (noticias generales del dashboard).
    const [hasTrackedSymbols, setHasTrackedSymbols] = useState(false);
    const [aiInsight, setAiInsight] = useState('');
    const [marketIndices, setMarketIndices] = useState<MarketIndex[]>([]);
    const [opportunities, setOpportunities] = useState<UndervaluedStock[]>([]);
    const [indicesLoading, setIndicesLoading] = useState(true);
    const [portfolioLoading, setPortfolioLoading] = useState(true);
    const [watchlistLoading, setWatchlistLoading] = useState(true);
    const [opportunitiesLoading, setOpportunitiesLoading] = useState(true);
    const [newsLoading, setNewsLoading] = useState(false);
    const [indicesError, setIndicesError] = useState<string | null>(null);
    const [portfolioError, setPortfolioError] = useState<string | null>(null);
    const [watchlistError, setWatchlistError] = useState<string | null>(null);
    const [opportunitiesError, setOpportunitiesError] = useState<string | null>(null);
    const [newsError, setNewsError] = useState<string | null>(null);

    useEffect(() => {
        let active = true;

        const loadData = async () => {
            setIndicesLoading(true);
            setPortfolioLoading(true);
            setWatchlistLoading(true);
            setOpportunitiesLoading(true);
            setNewsLoading(false);
            setIndicesError(null);
            setPortfolioError(null);
            setWatchlistError(null);
            setOpportunitiesError(null);
            setNewsError(null);

            // Las cuatro lecturas base no dependen entre sí. Lanzarlas juntas
            // elimina el waterfall del screener, cartera, watchlist e índices.
            let baseResults: [
                { data: Awaited<ReturnType<typeof getMarketIndices>>; error: string | null },
                { data: PortfolioSummary | null; error: string | null },
                { data: Awaited<ReturnType<typeof getWatchlist>>; error: string | null },
                { data: Awaited<ReturnType<typeof getScreenerStocksReal>>; error: string | null },
            ];
            try {
                baseResults = await Promise.all([
                    getMarketIndices().then((data) => ({ data, error: null as string | null })).catch((error) => ({ data: [] as Awaited<ReturnType<typeof getMarketIndices>>, error: sectionError(error) })),
                    getPortfolioSummary(userId).then((data) => ({ data, error: null as string | null })).catch((error) => ({ data: null as PortfolioSummary | null, error: sectionError(error) })),
                    getWatchlist().then((data) => ({ data, error: null as string | null })).catch((error) => ({ data: [] as Awaited<ReturnType<typeof getWatchlist>>, error: sectionError(error) })),
                    getScreenerStocksReal({
                        marketCapMoreThan: 10000000000,
                        sector: 'Technology',
                        limit: 10,
                    }).then((data) => ({ data, error: null as string | null })).catch((error) => ({ data: [] as Awaited<ReturnType<typeof getScreenerStocksReal>>, error: sectionError(error) })),
                ]);
            } catch (error) {
                if (!active) return;
                const message = sectionError(error);
                setIndicesError(message);
                setPortfolioError(message);
                setWatchlistError(message);
                setOpportunitiesError(message);
                setIndicesLoading(false);
                setPortfolioLoading(false);
                setWatchlistLoading(false);
                setOpportunitiesLoading(false);
                return;
            }
            const [indicesResult, summaryResult, watchlistResult, screenerResult] = baseResults;
            if (!active) return;

            setMarketIndices(indicesResult.data.map((data) => ({
                symbol: data.symbol,
                name: data.name,
                price: data.price || 0,
                change: data.change || 0,
                changePercent: data.changePercent || 0,
            })).filter((i) => i.price > 0));
            setIndicesLoading(false);
            setIndicesError(indicesResult.error);

            setPortfolioSummary(summaryResult.data);
            setPortfolioLoading(false);
            setPortfolioError(summaryResult.error);

            const watchlistItems = watchlistResult.data;
            setWatchlistError(watchlistResult.error);
            const portfolioSymbols = summaryResult.data?.holdings.map((h) => h.symbol) ?? [];
            const watchlistSymbols = watchlistItems.slice(0, 5).map((w) => w.symbol);
            const allUniqueSymbols = Array.from(new Set([...portfolioSymbols, ...watchlistSymbols]));
            setHasTrackedSymbols(allUniqueSymbols.length > 0);

            // Los candidatos sólo dependen del screener; sus cálculos de DCF y
            // quote sí se lanzan en paralelo por símbolo.
            const candidates = (screenerResult.data?.map((s) => s.symbol) ?? []).slice(0, 6);
            const opportunitiesPromise = Promise.all(candidates.map(async (sym: string) => {
                try {
                    const [fairValue, quote] = await Promise.all([getFairValue(sym), getStockQuote(sym)]);
                    const currentPrice = quote?.c || 0;
                    if (fairValue && currentPrice > 0) {
                        const upside = ((fairValue - currentPrice) / currentPrice) * 100;
                        return upside > 5
                            ? { symbol: sym, name: sym, price: currentPrice, fairValue, upside }
                            : null;
                    }
                    return null;
                } catch {
                    return null;
                }
            })).then((results) => results.filter((op): op is UndervaluedStock => op !== null).sort((a, b) => b.upside - a.upside).slice(0, 4));

            const watchlistPromise = Promise.all(watchlistItems.slice(0, 5).map(async (item): Promise<WatchlistItem> => {
                try {
                    const data = await getStockFinancialData(item.symbol);
                    return {
                        symbol: item.symbol,
                        name: data?.profile?.name || item.symbol,
                        price: data?.quote?.c || 0,
                        changePercent: data?.quote?.dp || 0,
                    };
                } catch {
                    return { symbol: item.symbol, name: item.symbol, price: 0, changePercent: 0 };
                }
            }));

            // Noticias, earnings y las dos Cards de símbolos se resuelven en
            // paralelo. Sólo el fallback general de noticias conserva su orden.
            const newsPromise = allUniqueSymbols.length > 0
                ? Promise.all(allUniqueSymbols.slice(0, 5).map((symbol) => getCompanyNews(symbol, 2).catch(() => []))).then(async (newsResults) => {
                    const allNews: NewsArticle[] = newsResults.flat();
                    if (allNews.length < 5) {
                        try {
                            allNews.push(...((await getNews()) || []));
                        } catch {
                            // La tarjeta muestra un vacío honesto si no hay fallback.
                        }
                    }
                    return allNews.slice(0, 6);
                }).then((data) => ({ data, error: null as string | null })).catch((error) => ({ data: [] as NewsArticle[], error: sectionError(error) }))
                : Promise.resolve({ data: [] as NewsArticle[], error: null as string | null });
            setNewsLoading(allUniqueSymbols.length > 0);
            const [opportunitiesResult, watchlistWithPrices, newsResult] = await Promise.all([
                opportunitiesPromise.then((data) => ({ data, error: null as string | null })).catch((error) => ({ data: [] as UndervaluedStock[], error: sectionError(error) })),
                watchlistPromise.then((data) => ({ data, error: null as string | null })).catch((error) => ({ data: [] as WatchlistItem[], error: sectionError(error) })),
                newsPromise,
                ]);
            if (!active) return;

            setOpportunities(opportunitiesResult.data);
            setOpportunitiesLoading(false);
            setOpportunitiesError(opportunitiesResult.error ?? screenerResult.error);
            setWatchlist(watchlistWithPrices.data);
            setWatchlistLoading(false);
            setWatchlistError(watchlistWithPrices.error ?? watchlistResult.error);
            setNews(newsResult.data);
            setNewsLoading(false);
            setNewsError(newsResult.error);
            // Earnings se resuelve para no bloquear el resto; esta tarjeta no lo renderiza.

            if (summaryResult.data && summaryResult.data.holdings.length > 0) {
                const summary = summaryResult.data;
                // F17: gainPercent es rentabilidad desde la compra (no la
                // variacion de hoy) y solo existe con base de coste. Sin
                // coste no hay frase de movimiento: un "0,00%" seria inventado.
                const conCoste = summary.holdings.filter((h) => h.cost > 0 && !h.fxMissing);
                if (conCoste.length === 0) {
                    setAiInsight('Todavía no tenemos la base de coste de tus posiciones. Cuando esté cargada, aquí verás cómo va tu cartera desde la compra.');
                } else {
                    const topMover = conCoste.reduce((a, b) => Math.abs(b.gainPercent) > Math.abs(a.gainPercent) ? b : a);
                    const costeTotal = conCoste.reduce((sum, h) => sum + h.cost, 0);
                    const gananciaTotal = conCoste.reduce((sum, h) => sum + h.gain, 0);
                    const totalPercent = costeTotal > 0 ? (gananciaTotal / costeTotal) * 100 : 0;
                    const direccion = totalPercent >= 0 ? 'una subida' : 'una caída';
                    setAiInsight(`Tu cartera acumula ${direccion} del ${formatPercent(totalPercent, { fromRatio: false, digits: 2, signDisplay: 'never' })} desde la compra. ${topMover.symbol} es la posición que más se mueve (${formatPercent(topMover.gainPercent, { fromRatio: false, digits: 2, signDisplay: 'always' })}).`);
                }
            } else {
                setAiInsight('');
            }
        };

        void loadData();
        return () => {
            active = false;
        };
        // reloadToken es un disparador explícito del botón Reintentar.
    }, [userId, reloadToken]);

    const retry = () => setReloadToken((value) => value + 1);

    // Derivados memorizados: evita reordenar el estado en cada render
    // (.sort() mutaba el array del estado) y recalcula solo si cambian los datos.
    const sortedHoldings = useMemo(() => {
        if (!portfolioSummary) return [];
        return [...portfolioSummary.holdings]
            .sort((a, b) => Math.abs(b.gainPercent) - Math.abs(a.gainPercent))
            .slice(0, 4);
    }, [portfolioSummary]);

    const visibleNews = useMemo(() => news.slice(0, 4), [news]);

    return (
        <div className="space-y-8">
            {/* Header Welcome */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 break-words">Bienvenido</h1>
                    <p className="text-gray-400 mt-1">Resumen de mercado y tus inversiones</p>
                </div>
            </div>

            {/* Market Indices Ticker */}
            <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-3 2xl:grid-cols-5 gap-4">
                {indicesLoading ? (
                    [1, 2, 3, 4].map((i) => <StockCardSkeleton key={i} />)
                ) : marketIndices.length > 0 ? marketIndices.map((index) => (
                    <MarketIndexCard key={index.symbol} index={index} />
                )) : indicesError ? (
                    <div className="md:col-span-3 xl:col-span-5">
                        <InlineSectionError message={indicesError} onRetry={retry} />
                    </div>
                ) : null}
            </div>

            {/* Main Content Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                {/* Left Column (2/3): Portfolio & Opportunities */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Insights & Portfolio */}
                    {aiInsight && (
                        <Card className="bg-gradient-to-r from-teal-900/40 to-blue-900/40 border-teal-800/50">
                            <CardContent className="p-4 flex flex-col min-[420px]:flex-row min-[420px]:items-center gap-4">
                                <div className="p-3 bg-teal-500/10 rounded-full">
                                    <Brain className="h-6 w-6 text-teal-400" />
                                </div>
                                <div>
                                    <h3 className="text-sm font-semibold text-teal-300 mb-1">Análisis de Cartera (IA)</h3>
                                    <p className="text-gray-200 text-sm leading-relaxed">{aiInsight}</p>
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    <Card className="bg-gray-800/50 border-gray-700">
                        <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-gray-700/50">
                            <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                                <Wallet className="h-5 w-5 text-blue-400" />
                                Tu Cartera Hoy
                            </CardTitle>
                            <Link href="/portfolio" className="inline-flex min-h-[44px] items-center gap-1 px-2 -mr-2 text-blue-400 hover:text-blue-300 text-sm transition-colors">
                                <span className="whitespace-nowrap">Ver detalles</span> <ArrowRight className="w-4 h-4 shrink-0" />
                            </Link>
                        </CardHeader>
                        <CardContent className="pt-4">
                            {portfolioLoading ? (
                                <div className="animate-pulse space-y-3" role="status" aria-label="Cargando cartera">
                                    <div className="h-16 rounded-xl bg-gray-800/60" />
                                    <div className="h-10 rounded-lg bg-gray-800/40" />
                                </div>
                            ) : portfolioError ? (
                                <InlineSectionError message={portfolioError} onRetry={retry} />
                            ) : portfolioSummary && portfolioSummary.holdings.length > 0 ? (
                                <div className="space-y-5">
                                    <div className="flex flex-col min-[420px]:flex-row min-[420px]:justify-between min-[420px]:items-center gap-3 p-4 bg-gray-900/60 rounded-xl border border-gray-700/50">
                                        <div className="min-w-0">
                                            <p className="text-sm text-gray-400">Valor Total Estimado</p>
                                            <p className="text-2xl sm:text-3xl font-bold text-white mt-1 break-words">{formatMoney(portfolioSummary.totalValue)}</p>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-sm text-gray-400">Ganancia/Pérdida Total</p>
                                            <p className={`text-xl font-bold mt-1 ${portfolioSummary.totalGainPercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                {formatPercent(portfolioSummary.totalGainPercent, { fromRatio: false, digits: 2, signDisplay: 'always' })}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                        {sortedHoldings
                                            .map((h) => (
                                                <Link
                                                    key={h.symbol}
                                                    href={`/research/${h.symbol}`}
                                                    prefetch
                                                    className="flex min-h-[44px] items-center justify-between gap-2 p-3 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors border border-gray-700/30"
                                                >
                                                    <span className="text-white font-semibold">{h.symbol}</span>
                                                    <span className={`font-mono ${h.cost > 0 ? (h.gainPercent >= 0 ? 'text-green-400' : 'text-red-400') : 'text-gray-500'}`}>
                                                        {h.cost > 0 ? formatPercent(h.gainPercent, { fromRatio: false, digits: 2, signDisplay: 'always' }) : 's/d'}
                                                    </span>
                                                </Link>
                                            ))}
                                    </div>
                                </div>
                            ) : (
                                <div className="text-center py-10">
                                    <div className="w-16 h-16 bg-gray-800 rounded-full flex items-center justify-center mx-auto mb-4">
                                        <Wallet className="h-8 w-8 text-gray-500" />
                                    </div>
                                    <h3 className="text-lg font-medium text-white mb-2">Comienza tu viaje</h3>
                                    <p className="text-gray-400 text-sm max-w-xs mx-auto mb-6">Añade tu primera inversión para ver análisis y métricas detalladas.</p>
                                    <Link href="/portfolio" className="inline-flex min-h-[44px] items-center justify-center bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-full transition-colors font-medium">
                                        Añadir inversión
                                    </Link>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Opportunities Section */}
                    {opportunitiesLoading ? (
                        <Card className="bg-gray-800/50 border-gray-700">
                            <CardContent className="pt-4"><div className="h-24 animate-pulse rounded-lg bg-gray-800/50" role="status" aria-label="Cargando oportunidades" /></CardContent>
                        </Card>
                    ) : opportunitiesError ? (
                        <InlineSectionError message={opportunitiesError} onRetry={retry} />
                    ) : opportunities.length > 0 ? (
                        <Card className="bg-gray-800/50 border-gray-700">
                            <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-gray-700/50">
                                <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                                    <Gem className="h-5 w-5 text-purple-400" />
                                    Gemas Infravaloradas (DCF)
                                </CardTitle>
                                <span className="text-xs text-gray-500 bg-gray-800 px-2 py-1 rounded">Basado en Valor Intrínseco</span>
                            </CardHeader>
                            <CardContent className="pt-4">
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    {opportunities.map((op) => (
                                        <Link key={op.symbol} href={`/research/${op.symbol}`} prefetch>
                                            <div className="p-4 bg-gray-900/40 rounded-xl border border-gray-700/30 hover:border-purple-500/50 hover:bg-gray-800 transition-all group">
                                                <div className="flex justify-between items-start mb-2">
                                                    <div>
                                                        <h4 className="font-bold text-white group-hover:text-purple-400 transition-colors">{op.symbol}</h4>
                                                        <p className="text-xs text-gray-400">Precio: {formatMoney(op.price)}</p>
                                                    </div>
                                                    <Badge className="bg-green-900/30 text-green-400 border-green-800">
                                                        {formatPercent(op.upside, { fromRatio: false, digits: 1, signDisplay: 'always' })} potencial
                                                    </Badge>
                                                </div>
                                                <div className="w-full bg-gray-800 h-1.5 rounded-full mt-2 overflow-hidden">
                                                    <div
                                                        className="h-full bg-gradient-to-r from-green-600 to-green-400"
                                                        style={{ width: `${Math.min(op.upside, 100)}%` }}
                                                    />
                                                </div>
                                                <p className="text-xs text-gray-500 mt-2 text-right">Valor justo: {formatMoney(op.fairValue)}</p>
                                            </div>
                                        </Link>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    ) : (
                        <Card className="bg-gray-800/50 border-gray-700">
                            <CardContent className="pt-4 text-sm text-gray-500">
                                No hay oportunidades que cumplan el filtro ahora.
                            </CardContent>
                        </Card>
                    )}
                </div>

                {/* Right Column (1/3): Watchlist & News */}
                <div className="space-y-6">
                    <Card className="bg-gray-800/50 border-gray-700">
                        <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-gray-700/50">
                            <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                                <Eye className="h-5 w-5 text-yellow-400" />
                                Watchlist
                            </CardTitle>
                            <Link href="/watchlist" aria-label="Ver watchlist completa" className="inline-flex min-h-[44px] min-w-[44px] items-center justify-end px-1 text-yellow-400 hover:text-yellow-300 text-sm transition-colors">
                                <ArrowRight className="w-4 h-4" />
                            </Link>
                        </CardHeader>
                        <CardContent className="pt-4">
                            {watchlistLoading ? (
                                <div className="space-y-2 animate-pulse" role="status" aria-label="Cargando watchlist">
                                    {[1, 2, 3].map((i) => <div key={i} className="h-12 rounded-lg bg-gray-800/50" />)}
                                </div>
                            ) : watchlistError ? (
                                <InlineSectionError message={watchlistError} onRetry={retry} />
                            ) : watchlist.length > 0 ? (
                                <div className="space-y-1">
                                    {watchlist.map((stock) => (
                                        <Link
                                            key={stock.symbol}
                                            href={`/research/${stock.symbol}`}
                                            prefetch
                                            className="flex min-h-[44px] items-center justify-between gap-2 p-3 bg-gray-900/30 rounded-lg hover:bg-gray-800/80 transition-colors group"
                                        >
                                            <div className="flex min-w-0 items-center gap-3">
                                                <div className={`shrink-0 p-2 rounded-full ${stock.changePercent >= 0 ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                                                    {stock.changePercent >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                                                </div>
                                                <div className="min-w-0">
                                                    <span className="block truncate text-white font-medium group-hover:text-yellow-400 transition-colors">{stock.symbol}</span>
                                                    <p className="block truncate max-w-[140px] sm:max-w-none text-xs text-gray-500" title={stock.name}>{stock.name}</p>
                                                </div>
                                            </div>
                                            <div className="shrink-0 text-right">
                                                <div className="text-white font-mono">{formatMoney(stock.price)}</div>
                                                <div className={`text-xs ${stock.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                    {formatPercent(stock.changePercent, { fromRatio: false, digits: 2, signDisplay: 'always' })}
                                                </div>
                                            </div>
                                        </Link>
                                    ))}
                                </div>
                            ) : (
                                <div className="text-center py-8">
                                    <p className="text-gray-400 text-sm">Lista vacía.</p>
                                    <Link href="/" className="text-yellow-400 text-xs mt-2 inline-block hover:underline">Buscar acciones</Link>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {hasTrackedSymbols && (
                    <Card className="bg-gray-800/50 border-gray-700">
                        <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-gray-700/50">
                            <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                                <Newspaper className="h-5 w-5 text-gray-400" />
                                Noticias
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-4">
                            {newsLoading ? (
                                <div className="space-y-3 animate-pulse" role="status" aria-label="Cargando noticias">
                                    {[1, 2, 3].map((i) => <div key={i} className="h-10 rounded-lg bg-gray-800/50" />)}
                                </div>
                            ) : newsError ? (
                                <InlineSectionError message={newsError} onRetry={retry} />
                            ) : news.length > 0 ? (
                                <div className="space-y-4">
                                    {visibleNews.map((article, i) => (
                                        <a
                                            key={i}
                                            href={article.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="block rounded-lg px-1 py-2 group"
                                        >
                                            <h4 title={article.headline} className="text-sm text-gray-200 group-hover:text-blue-400 transition-colors line-clamp-2 leading-snug">
                                                {article.headline}
                                            </h4>
                                            <div className="flex justify-between items-center mt-1">
                                                <span className="text-xs text-gray-500">{article.source}</span>
                                                <span className="text-xs text-gray-600">{article.datetime ? new Date(article.datetime * 1000).toLocaleDateString() : 'fecha desconocida'}</span>
                                            </div>
                                        </a>
                                    ))}
                                </div>
                            ) : (
                                <p className="text-gray-500 text-center py-4 text-sm">Sin noticias relevantes.</p>
                            )}
                        </CardContent>
                    </Card>
                    )}
                </div>
            </div>
        </div>
    );
}

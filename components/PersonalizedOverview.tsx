'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, Wallet, ArrowRight, Eye, Calendar, Newspaper, Brain, Sparkles, Loader2, BarChart3, Gem } from 'lucide-react';
import { getPortfolioSummary, getPortfolioScores, type PortfolioSummary } from '@/lib/actions/portfolio.actions';
import { getWatchlist } from '@/lib/actions/watchlist.actions';
import { getCompanyNews, getStockFinancialData, getUpcomingEarnings, getStockQuote, type EarningsEvent } from '@/lib/actions/finnhub.actions';
import { getValuationData, getScreenerStocks } from '@/lib/actions/fmp.actions';


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



export default function PersonalizedOverview({ userId }: PersonalizedOverviewProps) {
    const [loading, setLoading] = useState(true);
    const [portfolioSummary, setPortfolioSummary] = useState<PortfolioSummary | null>(null);
    const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
    const [news, setNews] = useState<any[]>([]);
    const [upcomingEarnings, setUpcomingEarnings] = useState<EarningsEvent[]>([]);
    const [aiInsight, setAiInsight] = useState('');
    const [marketIndices, setMarketIndices] = useState<MarketIndex[]>([]);
    const [opportunities, setOpportunities] = useState<UndervaluedStock[]>([]);

    useEffect(() => {
        const loadData = async () => {
            setLoading(true);
            try {
                // 1. Cargar Indices de Mercado (Paralelo)
                const indicesProm = Promise.all([
                    getStockQuote('SPY'),
                    getStockQuote('QQQ'),
                    getStockQuote('DIA')
                ]);

                // 2. Cargar Portfolio
                const summaryProm = getPortfolioSummary(userId);

                // 3. Cargar Watchlist
                const watchlistProm = getWatchlist();

                // 4. Buscar Oportunidades (Screener + DCF)
                const screenerRes = await getScreenerStocks({
                    marketCapMoreThan: 10000000000,
                    sector: 'Technology',
                    limit: 30
                });
                const candidates = screenerRes?.map((s: any) => s.symbol) || ['GOOGL', 'AMZN', 'META', 'AMD', 'NVDA'];

                const opportunitiesProm = Promise.all(
                    candidates.map(async (sym: string) => {
                        try {
                            const valData = await getValuationData(sym);
                            const quote = await getStockQuote(sym);
                            // valData.dcf is { symbol: string, dcf: [...] }
                            // We need to access the inner dcf array, then the first item's dcf value
                            const dcfValue = valData?.dcf?.dcf?.[0]?.dcf;
                            const currentPrice = quote?.c || 0;

                            if (dcfValue && currentPrice > 0) {
                                const upside = ((dcfValue - currentPrice) / currentPrice) * 100;
                                if (upside > 5) {
                                    return {
                                        symbol: sym,
                                        name: sym,
                                        price: currentPrice,
                                        fairValue: dcfValue,
                                        upside: upside
                                    };
                                }
                            }
                            return null;
                        } catch { return null; }
                    })
                );

                const [indicesData, summary, watchlistItems, opportunitiesResults] = await Promise.all([
                    indicesProm,
                    summaryProm,
                    watchlistProm,
                    opportunitiesProm
                ]);

                // Procesar Indices
                const indicesNames = ['S&P 500', 'Nasdaq 100', 'Dow Jones'];
                const indicesSymbols = ['SPY', 'QQQ', 'DIA'];
                const processedIndices = indicesData.map((data, i) => ({
                    symbol: indicesSymbols[i],
                    name: indicesNames[i],
                    price: data?.c || 0,
                    change: data?.d || 0,
                    changePercent: data?.dp || 0
                })).filter(i => i.price > 0);
                setMarketIndices(processedIndices);

                setPortfolioSummary(summary);

                // Procesar Oportunidades
                const validOpportunities = opportunitiesResults
                    .filter((op): op is UndervaluedStock => op !== null)
                    .sort((a, b) => b.upside - a.upside)
                    .slice(0, 4);
                setOpportunities(validOpportunities);

                // Procesar Watchlist
                const watchlistWithPrices: WatchlistItem[] = [];
                for (const item of watchlistItems.slice(0, 5)) {
                    try {
                        const data = await getStockFinancialData(item.symbol);
                        watchlistWithPrices.push({
                            symbol: item.symbol,
                            name: data?.profile?.name || item.symbol,
                            price: data?.quote?.c || 0,
                            changePercent: data?.quote?.dp || 0
                        });
                    } catch {
                        watchlistWithPrices.push({
                            symbol: item.symbol,
                            name: item.symbol,
                            price: 0,
                            changePercent: 0
                        });
                    }
                }
                setWatchlist(watchlistWithPrices);

                // Collect all symbols for News and Earnings
                const portfolioSymbols = summary.holdings.map(h => h.symbol);
                const watchlistSymbols = watchlistItems.slice(0, 5).map(w => w.symbol);
                const allUniqueSymbols = Array.from(new Set([...portfolioSymbols, ...watchlistSymbols]));

                if (allUniqueSymbols.length > 0) {
                    // Cargar noticias y earnings si hay acciones
                    const newsSymbols = allUniqueSymbols.slice(0, 5);
                    const allNews: any[] = [];
                    // Using default fetch for company news
                    for (const symbol of newsSymbols) {
                        try {
                            const symbolNews = await getCompanyNews(symbol, 2);
                            allNews.push(...symbolNews);
                        } catch { }
                    }
                    if (allNews.length < 5) {
                        // Fallback global news
                        // Implementar fetch general news si hace falta
                    }
                    setNews(allNews.slice(0, 6));

                    try {
                        const earnings = await getUpcomingEarnings(allUniqueSymbols);
                        setUpcomingEarnings(earnings.slice(0, 3));
                    } catch (e) { console.error("Earnings error", e); }
                } else {
                    // Cargar noticias generales si no hay acciones
                    // (Podríamos implementar un getGeneralNews() aquí)
                }

                // Generar insight IA
                if (summary.holdings.length > 0) {
                    const topMover = summary.holdings.reduce((a, b) =>
                        Math.abs(b.gainPercent) > Math.abs(a.gainPercent) ? b : a
                    );
                    const direction = summary.totalGainPercent >= 0 ? 'sube' : 'baja';
                    setAiInsight(
                        `Hoy tu cartera ${direction} ${Math.abs(summary.totalGainPercent).toFixed(2)}%. ` +
                        `${topMover.symbol} lidera con ${topMover.gainPercent >= 0 ? '+' : ''}${topMover.gainPercent.toFixed(2)}%.`
                    );
                }
            } catch (error) {
                console.error('Error loading overview:', error);
            }
            setLoading(false);
        };

        loadData();
    }, [userId]);

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[400px]">
                <Loader2 className="h-10 w-10 animate-spin text-teal-500" />
                <span className="ml-3 text-gray-400 text-lg">Preparando tu dashboard de mercado...</span>
            </div>
        );
    }

    return (
        <div className="space-y-8">
            {/* Header Welcome */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-gray-100">Bienvenido</h1>
                    <p className="text-gray-400 mt-1">Resumen de mercado y tus inversiones</p>
                </div>
                <div className="flex gap-2">
                    <Badge className="bg-teal-600/20 text-teal-400 border-teal-600/50 hover:bg-teal-600/30">
                        <Sparkles className="w-4 h-4 mr-2" />
                        AI Market Analysis
                    </Badge>
                </div>
            </div>

            {/* Market Indices Ticker */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {marketIndices.map((index) => (
                    <Card key={index.symbol} className="bg-gray-800/40 border-gray-700/50 hover:bg-gray-800/60 transition-colors">
                        <CardContent className="p-4 flex items-center justify-between">
                            <div>
                                <p className="text-sm text-gray-400 font-medium">{index.name}</p>
                                <p className="text-xl font-bold text-white mt-1">${index.price.toFixed(2)}</p>
                            </div>
                            <div className={`text-right ${index.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                <div className="flex items-center justify-end gap-1">
                                    {index.changePercent >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                                    <span className="font-bold">{Math.abs(index.changePercent).toFixed(2)}%</span>
                                </div>
                                <p className="text-xs mt-1">{index.change >= 0 ? '+' : ''}{index.change.toFixed(2)}</p>
                            </div>
                        </CardContent>
                    </Card>
                ))}
            </div>

            {/* Main Content Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                {/* Left Column (2/3): Portfolio & Opportunities */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Insights & Portfolio */}
                    {aiInsight && (
                        <Card className="bg-gradient-to-r from-teal-900/40 to-blue-900/40 border-teal-800/50">
                            <CardContent className="p-4 flex items-center gap-4">
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
                            <Link href="/portfolio" className="text-blue-400 hover:text-blue-300 text-sm flex items-center gap-1 transition-colors">
                                Ver detalles <ArrowRight className="w-4 h-4" />
                            </Link>
                        </CardHeader>
                        <CardContent className="pt-4">
                            {portfolioSummary && portfolioSummary.holdings.length > 0 ? (
                                <div className="space-y-5">
                                    <div className="flex justify-between items-center p-4 bg-gray-900/60 rounded-xl border border-gray-700/50">
                                        <div>
                                            <p className="text-sm text-gray-400">Valor Total Estimado</p>
                                            <p className="text-3xl font-bold text-white mt-1">${portfolioSummary.totalValue.toLocaleString('en-US', { minimumFractionDigits: 2 })}</p>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-sm text-gray-400">Ganancia/Pérdida Total</p>
                                            <p className={`text-xl font-bold mt-1 ${portfolioSummary.totalGainPercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                {portfolioSummary.totalGainPercent >= 0 ? '+' : ''}{portfolioSummary.totalGainPercent.toFixed(2)}%
                                            </p>
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                        {portfolioSummary.holdings
                                            .sort((a, b) => Math.abs(b.gainPercent) - Math.abs(a.gainPercent))
                                            .slice(0, 4)
                                            .map((h) => (
                                                <Link
                                                    key={h.symbol}
                                                    href={`/stocks/${h.symbol}`}
                                                    className="flex items-center justify-between p-3 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors border border-gray-700/30"
                                                >
                                                    <span className="text-white font-semibold">{h.symbol}</span>
                                                    <span className={`font-mono ${h.gainPercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                        {h.gainPercent >= 0 ? '+' : ''}{h.gainPercent.toFixed(2)}%
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
                                    <Link href="/portfolio" className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-full transition-colors font-medium">
                                        Añadir Inversiones
                                    </Link>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Opportunities Section */}
                    {opportunities.length > 0 && (
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
                                        <Link key={op.symbol} href={`/stocks/${op.symbol}`}>
                                            <div className="p-4 bg-gray-900/40 rounded-xl border border-gray-700/30 hover:border-purple-500/50 hover:bg-gray-800 transition-all group">
                                                <div className="flex justify-between items-start mb-2">
                                                    <div>
                                                        <h4 className="font-bold text-white group-hover:text-purple-400 transition-colors">{op.symbol}</h4>
                                                        <p className="text-xs text-gray-400">Precio: ${op.price.toFixed(2)}</p>
                                                    </div>
                                                    <Badge className="bg-green-900/30 text-green-400 border-green-800">
                                                        +{op.upside.toFixed(1)}% Upside
                                                    </Badge>
                                                </div>
                                                <div className="w-full bg-gray-800 h-1.5 rounded-full mt-2 overflow-hidden">
                                                    <div
                                                        className="h-full bg-gradient-to-r from-green-600 to-green-400"
                                                        style={{ width: `${Math.min(op.upside, 100)}%` }}
                                                    />
                                                </div>
                                                <p className="text-xs text-gray-500 mt-2 text-right">Valor Justo: ${op.fairValue.toFixed(2)}</p>
                                            </div>
                                        </Link>
                                    ))}
                                </div>
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
                            <Link href="/watchlist" className="text-yellow-400 hover:text-yellow-300 text-sm flex items-center gap-1 transition-colors">
                                <ArrowRight className="w-4 h-4" />
                            </Link>
                        </CardHeader>
                        <CardContent className="pt-4">
                            {watchlist.length > 0 ? (
                                <div className="space-y-1">
                                    {watchlist.map((stock) => (
                                        <Link
                                            key={stock.symbol}
                                            href={`/stocks/${stock.symbol}`}
                                            className="flex items-center justify-between p-3 bg-gray-900/30 rounded-lg hover:bg-gray-800/80 transition-colors group"
                                        >
                                            <div className="flex items-center gap-3">
                                                <div className={`p-2 rounded-full ${stock.changePercent >= 0 ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                                                    {stock.changePercent >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                                                </div>
                                                <div>
                                                    <span className="text-white font-medium group-hover:text-yellow-400 transition-colors">{stock.symbol}</span>
                                                    <p className="text-xs text-gray-500 hidden sm:block">{stock.name.slice(0, 15)}...</p>
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <div className="text-white font-mono">${stock.price.toFixed(2)}</div>
                                                <div className={`text-xs ${stock.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                    {stock.changePercent >= 0 ? '+' : ''}{stock.changePercent.toFixed(2)}%
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

                    <Card className="bg-gray-800/50 border-gray-700">
                        <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-gray-700/50">
                            <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                                <Newspaper className="h-5 w-5 text-gray-400" />
                                Noticias
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-4">
                            {news.length > 0 ? (
                                <div className="space-y-4">
                                    {news.slice(0, 4).map((article, i) => (
                                        <a
                                            key={i}
                                            href={article.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="block group"
                                        >
                                            <h4 className="text-sm text-gray-200 group-hover:text-blue-400 transition-colors line-clamp-2 leading-snug">
                                                {article.headline}
                                            </h4>
                                            <div className="flex justify-between items-center mt-1">
                                                <span className="text-xs text-gray-500">{article.source}</span>
                                                <span className="text-xs text-gray-600">{new Date(article.datetime * 1000).toLocaleDateString()}</span>
                                            </div>
                                        </a>
                                    ))}
                                </div>
                            ) : (
                                <p className="text-gray-500 text-center py-4 text-sm">Sin noticias relevantes.</p>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}

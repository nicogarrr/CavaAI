'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, Wallet, ArrowRight, Eye, Calendar, Newspaper, Brain, Sparkles, Loader2 } from 'lucide-react';
import { getPortfolioSummary, getPortfolioScores, type PortfolioSummary } from '@/lib/actions/portfolio.actions';
import { getWatchlist } from '@/lib/actions/watchlist.actions';
import { getCompanyNews } from '@/lib/actions/finnhub.actions';
import { getStockFinancialData } from '@/lib/actions/finnhub.actions';

interface PersonalizedOverviewProps {
    userId: string;
}

interface WatchlistItem {
    symbol: string;
    name: string;
    price: number;
    changePercent: number;
}

export default function PersonalizedOverview({ userId }: PersonalizedOverviewProps) {
    const [loading, setLoading] = useState(true);
    const [portfolioSummary, setPortfolioSummary] = useState<PortfolioSummary | null>(null);
    const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
    const [news, setNews] = useState<any[]>([]);
    const [aiInsight, setAiInsight] = useState('');

    useEffect(() => {
        const loadData = async () => {
            setLoading(true);
            try {
                // Cargar portfolio
                const summary = await getPortfolioSummary(userId);
                setPortfolioSummary(summary);

                // Cargar watchlist con precios
                const watchlistItems = await getWatchlist();
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

                // Cargar noticias de acciones del usuario
                const allSymbols = [
                    ...summary.holdings.map(h => h.symbol),
                    ...watchlistItems.slice(0, 3).map(w => w.symbol)
                ].slice(0, 5);

                const allNews: any[] = [];
                for (const symbol of allSymbols) {
                    try {
                        const symbolNews = await getCompanyNews(symbol, 2);
                        allNews.push(...symbolNews);
                    } catch { }
                }
                setNews(allNews.slice(0, 6));

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
                <Loader2 className="h-8 w-8 animate-spin text-teal-500" />
                <span className="ml-3 text-gray-400">Cargando tu overview personalizado...</span>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-gray-100">👋 Bienvenido</h1>
                    <p className="text-gray-400 mt-1">Tu resumen personalizado de inversiones</p>
                </div>
                <Badge className="bg-teal-600 text-white px-4 py-2">
                    <Sparkles className="w-4 h-4 mr-2" />
                    Personalizado para ti
                </Badge>
            </div>

            {/* AI Insight */}
            {aiInsight && (
                <Card className="bg-gradient-to-r from-teal-900/50 to-purple-900/50 border-teal-700">
                    <CardContent className="p-4 flex items-center gap-3">
                        <Brain className="h-8 w-8 text-teal-400" />
                        <div>
                            <h3 className="text-sm font-medium text-teal-300">🤖 Análisis IA</h3>
                            <p className="text-gray-200">{aiInsight}</p>
                        </div>
                    </CardContent>
                </Card>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Tu Cartera Hoy */}
                <Card className="bg-gray-800/50 border-gray-700">
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                            <Wallet className="h-5 w-5 text-teal-400" />
                            Tu Cartera Hoy
                        </CardTitle>
                        <Link href="/portfolio" className="text-teal-400 hover:text-teal-300 text-sm flex items-center gap-1">
                            Ver todo <ArrowRight className="w-4 h-4" />
                        </Link>
                    </CardHeader>
                    <CardContent>
                        {portfolioSummary && portfolioSummary.holdings.length > 0 ? (
                            <div className="space-y-4">
                                {/* Resumen */}
                                <div className="flex justify-between items-center p-4 bg-gray-900 rounded-lg">
                                    <div>
                                        <p className="text-sm text-gray-400">Valor Total</p>
                                        <p className="text-2xl font-bold text-white">${portfolioSummary.totalValue.toFixed(2)}</p>
                                    </div>
                                    <div className="text-right">
                                        <p className="text-sm text-gray-400">P&L</p>
                                        <p className={`text-xl font-bold ${portfolioSummary.totalGainPercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {portfolioSummary.totalGainPercent >= 0 ? '+' : ''}{portfolioSummary.totalGainPercent.toFixed(2)}%
                                        </p>
                                    </div>
                                </div>

                                {/* Top movers */}
                                <div className="space-y-2">
                                    <p className="text-sm text-gray-400">Mayores movimientos</p>
                                    {portfolioSummary.holdings
                                        .sort((a, b) => Math.abs(b.gainPercent) - Math.abs(a.gainPercent))
                                        .slice(0, 3)
                                        .map((h) => (
                                            <Link
                                                key={h.symbol}
                                                href={`/stocks/${h.symbol}`}
                                                className="flex items-center justify-between p-2 bg-gray-900/50 rounded hover:bg-gray-900 transition-colors"
                                            >
                                                <span className="text-white font-medium">{h.symbol}</span>
                                                <span className={`${h.gainPercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                    {h.gainPercent >= 0 ? '+' : ''}{h.gainPercent.toFixed(2)}%
                                                </span>
                                            </Link>
                                        ))}
                                </div>
                            </div>
                        ) : (
                            <div className="text-center py-8">
                                <Wallet className="h-12 w-12 mx-auto text-gray-600 mb-3" />
                                <p className="text-gray-400">Tu cartera está vacía</p>
                                <Link href="/portfolio" className="text-teal-400 hover:underline text-sm">
                                    Añadir inversiones →
                                </Link>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Tu Watchlist Rápida */}
                <Card className="bg-gray-800/50 border-gray-700">
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                            <Eye className="h-5 w-5 text-purple-400" />
                            Tu Watchlist
                        </CardTitle>
                        <Link href="/watchlist" className="text-teal-400 hover:text-teal-300 text-sm flex items-center gap-1">
                            Ver todo <ArrowRight className="w-4 h-4" />
                        </Link>
                    </CardHeader>
                    <CardContent>
                        {watchlist.length > 0 ? (
                            <div className="space-y-2">
                                {watchlist.map((stock) => (
                                    <Link
                                        key={stock.symbol}
                                        href={`/stocks/${stock.symbol}`}
                                        className="flex items-center justify-between p-3 bg-gray-900/50 rounded-lg hover:bg-gray-900 transition-colors"
                                    >
                                        <div className="flex items-center gap-3">
                                            {stock.changePercent >= 0 ? (
                                                <TrendingUp className="w-4 h-4 text-green-400" />
                                            ) : (
                                                <TrendingDown className="w-4 h-4 text-red-400" />
                                            )}
                                            <div>
                                                <span className="text-white font-medium">{stock.symbol}</span>
                                                <span className="text-gray-500 text-sm ml-2">{stock.name.slice(0, 20)}</span>
                                            </div>
                                        </div>
                                        <div className="text-right">
                                            <div className="text-white">${stock.price.toFixed(2)}</div>
                                            <div className={`text-sm ${stock.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                {stock.changePercent >= 0 ? '+' : ''}{stock.changePercent.toFixed(2)}%
                                            </div>
                                        </div>
                                    </Link>
                                ))}
                            </div>
                        ) : (
                            <div className="text-center py-8">
                                <Eye className="h-12 w-12 mx-auto text-gray-600 mb-3" />
                                <p className="text-gray-400">Tu watchlist está vacía</p>
                                <p className="text-gray-500 text-sm">Busca acciones y añádelas a tu watchlist</p>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Noticias de TUS acciones */}
            <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                        <Newspaper className="h-5 w-5 text-blue-400" />
                        Noticias de Tus Acciones
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    {news.length > 0 ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {news.map((article, i) => (
                                <a
                                    key={`${article.id || i}-${article.headline?.slice(0, 10)}`}
                                    href={article.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="block p-4 bg-gray-900/50 rounded-lg hover:bg-gray-900 transition-colors"
                                >
                                    <p className="text-white text-sm line-clamp-2 mb-2">{article.headline}</p>
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs text-gray-500">{article.source}</span>
                                        <span className="text-xs text-teal-400">{article.related}</span>
                                    </div>
                                </a>
                            ))}
                        </div>
                    ) : (
                        <div className="text-center py-8">
                            <Newspaper className="h-12 w-12 mx-auto text-gray-600 mb-3" />
                            <p className="text-gray-400">No hay noticias recientes de tus acciones</p>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Eventos Próximos */}
            <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader className="pb-2">
                    <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                        <Calendar className="h-5 w-5 text-yellow-400" />
                        Próximos Eventos
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    {portfolioSummary && portfolioSummary.holdings.length > 0 ? (
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {portfolioSummary.holdings.slice(0, 3).map((h) => (
                                <div key={h.symbol} className="p-4 bg-gray-900/50 rounded-lg">
                                    <div className="flex items-center gap-2 mb-2">
                                        <span className="text-white font-medium">{h.symbol}</span>
                                        <Badge className="bg-yellow-600/30 text-yellow-300 text-xs">Próximo</Badge>
                                    </div>
                                    <p className="text-sm text-gray-400">Earnings pendientes</p>
                                    <p className="text-xs text-gray-500 mt-1">Consulta el calendario de earnings</p>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="text-center py-6">
                            <Calendar className="h-10 w-10 mx-auto text-gray-600 mb-2" />
                            <p className="text-gray-400 text-sm">Añade acciones a tu cartera para ver eventos</p>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}

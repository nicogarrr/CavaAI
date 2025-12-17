import TradingViewWidget from "@/components/TradingViewWidget";
import WatchlistButton from "@/components/WatchlistButton";
import StockNews from "@/components/stocks/StockNews";
import HealthScore from "@/components/stocks/HealthScore";
import StockAnalysisDashboard from "@/components/stocks/StockAnalysisDashboard";
import StockFinancials from "@/components/stocks/StockFinancials";
import { getProfile, getStockQuote } from "@/lib/actions/finnhub.actions";
import { Suspense } from 'react';
import { Skeleton } from "@/components/ui/skeleton";
import {
    SYMBOL_INFO_WIDGET_CONFIG,
    CANDLE_CHART_WIDGET_CONFIG,
    TECHNICAL_ANALYSIS_WIDGET_CONFIG,
} from "@/lib/constants";

export default async function StockDetails({ params }: StockDetailsPageProps) {
    const { symbol } = await params;
    const scriptUrl = `https://s3.tradingview.com/external-embedding/embed-widget-`;

    // 1. Parallelize initial critical data fetching (Header & Basic Info)
    const profilePromise = getProfile(symbol);
    const quotePromise = getStockQuote(symbol);

    // Obtener estado de watchlist
    const { getWatchlist } = await import("@/lib/actions/watchlist.actions");
    const watchlistPromise = getWatchlist();

    const [profile, quote, watchlist] = await Promise.all([
        profilePromise,
        quotePromise,
        watchlistPromise
    ]);

    const isInWatchlist = watchlist.some((item) => item.symbol === symbol.toUpperCase());
    const companyName = profile?.name || symbol;
    const currentPrice = quote?.c || 0;
    const upperSymbol = symbol.toUpperCase();

    return (
        <div className="flex min-h-screen flex-col gap-6">
            {/* Header Section - Loads Immediately */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-gray-700">
                <div className="flex flex-col gap-2">
                    <h1 className="text-3xl font-bold text-gray-100">{companyName}</h1>
                    <p className="text-lg text-gray-400">{upperSymbol}</p>
                </div>
                <div className="flex items-center gap-4">
                    {currentPrice > 0 && (
                        <div className="text-right">
                            <p className="text-2xl font-semibold text-gray-100">${currentPrice.toFixed(2)}</p>
                        </div>
                    )}
                    <WatchlistButton
                        symbol={upperSymbol}
                        company={companyName}
                        isInWatchlist={isInWatchlist}
                    />
                </div>
            </div>

            {/* Main Content Grid */}
            <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left Column - Main Chart (2/3 width) */}
                <div className="lg:col-span-2 flex flex-col gap-6">
                    {/* Symbol Info */}
                    <div className="min-h-[170px]">
                        <TradingViewWidget
                            scriptUrl={`${scriptUrl}symbol-info.js`}
                            config={SYMBOL_INFO_WIDGET_CONFIG(symbol)}
                            height={170}
                        />
                    </div>

                    {/* Main Chart */}
                    <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-4 min-h-[650px]">
                        <TradingViewWidget
                            scriptUrl={`${scriptUrl}advanced-chart.js`}
                            config={CANDLE_CHART_WIDGET_CONFIG(symbol)}
                            className="custom-chart"
                            height={650}
                        />
                    </div>

                    {/* Stock News - Internal Suspense or Fast enough? 
                        Let's keep it here. StockNews fetches its own data.
                    */}
                    <Suspense fallback={<Skeleton className="h-[400px] w-full rounded-lg bg-gray-800/50" />}>
                        <StockNews symbol={upperSymbol} />
                    </Suspense>
                </div>

                {/* Right Column - Sidebar (1/3 width) */}
                <div className="flex flex-col gap-6">
                    {/* Health Score */}
                    <Suspense fallback={<Skeleton className="h-[200px] w-full rounded-lg bg-gray-800/50" />}>
                        <HealthScore symbol={upperSymbol} />
                    </Suspense>

                    {/* Technical Analysis */}
                    <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                        <h2 className="text-lg font-semibold mb-4 text-gray-200">Análisis Técnico</h2>
                        <TradingViewWidget
                            scriptUrl={`${scriptUrl}technical-analysis.js`}
                            config={TECHNICAL_ANALYSIS_WIDGET_CONFIG(symbol)}
                            height={400}
                        />
                    </div>



                    {/* Financials (Native Component with Streaming) */}
                    <Suspense fallback={
                        <div className="space-y-4">
                            <Skeleton className="h-[200px] w-full rounded-lg bg-gray-800/50" />
                        </div>
                    }>
                        <StockFinancials symbol={upperSymbol} />
                    </Suspense>
                </div>
            </section>

            {/* Heavy Analysis Sections - Streamed via Suspense */}
            <Suspense fallback={
                <div className="flex flex-col gap-6 w-full">
                    {/* Skeleton for AI Checklist */}
                    <Skeleton className="h-[200px] w-full rounded-lg bg-gray-800/50" />
                    {/* Skeleton for Pattern Analysis */}
                    <Skeleton className="h-[400px] w-full rounded-lg bg-gray-800/50" />
                    {/* Skeleton for Alternatives */}
                    <Skeleton className="h-[300px] w-full rounded-lg bg-gray-800/50" />
                    {/* Skeleton for Deep Analysis */}
                    <Skeleton className="h-[600px] w-full rounded-lg bg-gray-800/50" />
                </div>
            }>
                <StockAnalysisDashboard
                    symbol={upperSymbol}
                    companyName={companyName}
                    currentPrice={currentPrice}
                />
            </Suspense>
        </div>
    );
}
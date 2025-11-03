import { Suspense } from 'react';
import NewsSection from "@/components/NewsSection";
import LazyTradingViewWidget from "@/components/LazyTradingViewWidget";
import { NewsLoadingSkeleton } from "@/components/LoadingState";
import {
    HEATMAP_WIDGET_CONFIG,
    MARKET_DATA_WIDGET_CONFIG,
    MARKET_OVERVIEW_WIDGET_CONFIG,
    NEWS_SYMBOLS
} from "@/lib/constants";

// Forzar renderizado dinámico porque puede requerir datos de usuario
export const dynamic = 'force-dynamic';
export const revalidate = 0;

const Home = () => {
    const scriptUrl = `https://s3.tradingview.com/external-embedding/embed-widget-`;

    return (
        <div className="flex min-h-screen home-wrapper">
            <section className="grid w-full gap-8 home-section">
                <div className="md:col-span-1 xl:col-span-1">
                    {/* Carga inmediatamente (prioridad) */}
                    <LazyTradingViewWidget
                        title="Market Overview"
                        scriptUrl={`${scriptUrl}market-overview.js`}
                        config={MARKET_OVERVIEW_WIDGET_CONFIG}
                        className="custom-chart"
                        height={600}
                        priority={true}
                    />
                </div>
                <div className="md-col-span xl:col-span-2">
                    {/* Lazy load cuando esté en viewport */}
                    <LazyTradingViewWidget
                        title="Stock Heatmap"
                        scriptUrl={`${scriptUrl}stock-heatmap.js`}
                        config={HEATMAP_WIDGET_CONFIG}
                        height={600}
                        priority={false}
                    />
                </div>
            </section>
            <section className="grid w-full gap-8 home-section">
                <div className="h-full md:col-span-1 xl:col-span-2">
                    {/* Lazy load cuando esté en viewport */}
                    <LazyTradingViewWidget
                        scriptUrl={`${scriptUrl}market-quotes.js`}
                        config={MARKET_DATA_WIDGET_CONFIG}
                        height={600}
                        priority={false}
                    />
                </div>
                <div className="h-full md:col-span-1 xl:col-span-1">
                    <Suspense fallback={<NewsLoadingSkeleton />}>
                        <NewsSection symbols={NEWS_SYMBOLS} />
                    </Suspense>
                </div>
            </section>
        </div>
    )
}

export default Home;
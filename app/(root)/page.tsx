import dynamicImport from 'next/dynamic';
import NewsSection from "@/components/NewsSection";
import LazyTradingViewWidget from "@/components/LazyTradingViewWidget";
import {
    HEATMAP_WIDGET_CONFIG,
    MARKET_DATA_WIDGET_CONFIG,
    MARKET_OVERVIEW_WIDGET_CONFIG,
    NEWS_SYMBOLS
} from "@/lib/constants";

// Forzar renderizado dinámico porque puede requerir datos de usuario
export const dynamic = 'force-dynamic';
export const revalidate = 0;

// Lazy load ProPicksSection solo cuando sea necesario
const LazyProPicksSection = dynamicImport(
    () => import("@/components/proPicks/ProPicksSection"),
    {
        ssr: true,
        loading: () => (
            <div className="w-full bg-gray-800 rounded-lg border border-gray-700 p-6">
                <div className="animate-pulse space-y-4">
                    <div className="h-8 bg-gray-700 rounded w-1/3"></div>
                    <div className="h-4 bg-gray-700 rounded w-2/3"></div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
                        {[1, 2, 3, 4].map((i) => (
                            <div key={i} className="h-32 bg-gray-700 rounded"></div>
                        ))}
                    </div>
                </div>
            </div>
        )
    }
);

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
                    <NewsSection symbols={NEWS_SYMBOLS} />
                </div>
            </section>

            {/* ProPicks IA Section - Lazy load cuando esté en viewport */}
            <section className="w-full mt-8">
                <LazyProPicksSection />
            </section>
        </div>
    )
}

export default Home;
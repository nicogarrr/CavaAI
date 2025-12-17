import TradingViewWidget from "@/components/TradingViewWidget";
import WatchlistButton from "@/components/WatchlistButton";
import AnalysisWrapper from "@/components/stocks/AnalysisWrapper";
import StockNews from "@/components/stocks/StockNews";
import HealthScore from "@/components/stocks/HealthScore";
import AIChecklistSection from "@/components/stocks/AIChecklistSection";
import PatternAnalysisSection from "@/components/stocks/PatternAnalysisSection";
import AlternativesSection from "@/components/stocks/AlternativesSection";
import { getProfile, getStockFinancialData } from "@/lib/actions/finnhub.actions";
import {
    SYMBOL_INFO_WIDGET_CONFIG,
    CANDLE_CHART_WIDGET_CONFIG,
    TECHNICAL_ANALYSIS_WIDGET_CONFIG,
    COMPANY_PROFILE_WIDGET_CONFIG,
    COMPANY_FINANCIALS_WIDGET_CONFIG,
} from "@/lib/constants";

export default async function StockDetails({ params }: StockDetailsPageProps) {
    const { symbol } = await params;
    const scriptUrl = `https://s3.tradingview.com/external-embedding/embed-widget-`;

    // Obtener datos de la empresa para el análisis DCF
    const profile = await getProfile(symbol);
    const financialData = await getStockFinancialData(symbol);

    const companyName = profile?.name || symbol;
    const currentPrice = financialData?.quote?.c || financialData?.quote?.price || 0;
    const upperSymbol = symbol.toUpperCase();

    return (
        <div className="flex min-h-screen flex-col gap-6">
            {/* Header Section */}
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
                        isInWatchlist={false}
                    />
                </div>
            </div>

            {/* Main Content Grid */}
            <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left Column - Main Chart (2/3 width) */}
                <div className="lg:col-span-2 flex flex-col gap-6">
                    {/* Symbol Info */}
                    <TradingViewWidget
                        scriptUrl={`${scriptUrl}symbol-info.js`}
                        config={SYMBOL_INFO_WIDGET_CONFIG(symbol)}
                        height={170}
                    />

                    {/* Main Chart */}
                    <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                        <TradingViewWidget
                            scriptUrl={`${scriptUrl}advanced-chart.js`}
                            config={CANDLE_CHART_WIDGET_CONFIG(symbol)}
                            className="custom-chart"
                            height={650}
                        />
                    </div>

                    {/* Stock News */}
                    <StockNews symbol={upperSymbol} />
                </div>

                {/* Right Column - Sidebar (1/3 width) */}
                <div className="flex flex-col gap-6">
                    {/* Health Score */}
                    <HealthScore symbol={upperSymbol} />

                    {/* Technical Analysis */}
                    <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                        <h2 className="text-lg font-semibold mb-4 text-gray-200">Análisis Técnico</h2>
                        <TradingViewWidget
                            scriptUrl={`${scriptUrl}technical-analysis.js`}
                            config={TECHNICAL_ANALYSIS_WIDGET_CONFIG(symbol)}
                            height={400}
                        />
                    </div>

                    {/* Company Profile */}
                    <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                        <h2 className="text-lg font-semibold mb-4 text-gray-200">Perfil de la Empresa</h2>
                        <TradingViewWidget
                            scriptUrl={`${scriptUrl}company-profile.js`}
                            config={COMPANY_PROFILE_WIDGET_CONFIG(symbol)}
                            height={440}
                        />
                    </div>

                    {/* Financials */}
                    <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                        <h2 className="text-lg font-semibold mb-4 text-gray-200">Estados Financieros</h2>
                        <TradingViewWidget
                            scriptUrl={`${scriptUrl}financials.js`}
                            config={COMPANY_FINANCIALS_WIDGET_CONFIG(symbol)}
                            height={700}
                        />
                    </div>
                </div>
            </section>

            {/* AI Checklist Section - Full Width */}
            <section className="w-full">
                <AIChecklistSection
                    symbol={upperSymbol}
                    companyName={companyName}
                    financialData={financialData}
                    currentPrice={currentPrice}
                />
            </section>

            {/* Pattern Analysis Section - Full Width */}
            <section className="w-full">
                <PatternAnalysisSection
                    symbol={upperSymbol}
                    companyName={companyName}
                    financialData={financialData}
                    currentPrice={currentPrice}
                />
            </section>

            {/* Alternatives Section - Full Width */}
            <section className="w-full">
                <AlternativesSection
                    symbol={upperSymbol}
                    companyName={companyName}
                    sector={(financialData?.profile as any)?.finnhubIndustry || (financialData?.profile as any)?.industry || ''}
                    financialData={financialData}
                    currentPrice={currentPrice}
                />
            </section>

            {/* Analysis Section - Full Width */}
            <section className="w-full">
                <AnalysisWrapper
                    symbol={upperSymbol}
                    companyName={companyName}
                    currentPrice={currentPrice}
                />
            </section>
        </div>
    );
}
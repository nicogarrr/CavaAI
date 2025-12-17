'use client';

import { useState, Suspense, lazy } from 'react';
import dynamic from 'next/dynamic';
import StockSidebar, { StockTab } from './StockSidebar';
import { Skeleton } from '@/components/ui/skeleton';
import TradingViewWidget from '@/components/TradingViewWidget';
import {
    SYMBOL_INFO_WIDGET_CONFIG,
    CANDLE_CHART_WIDGET_CONFIG,
    TECHNICAL_ANALYSIS_WIDGET_CONFIG,
} from '@/lib/constants';

// Lazy load heavy components - only load when tab is active
const StockValuation = dynamic(() => import('./StockValuation'), {
    loading: () => <TabSkeleton />,
    ssr: false,
});

const StockFundamentals = dynamic(() => import('./StockFundamentals'), {
    loading: () => <TabSkeleton />,
    ssr: false,
});

const HealthScore = dynamic(() => import('./HealthScore'), {
    loading: () => <Skeleton className="h-[200px] w-full rounded-lg bg-gray-800/50" />,
    ssr: false,
});

const StockFinancials = dynamic(() => import('./StockFinancials'), {
    loading: () => <Skeleton className="h-[300px] w-full rounded-lg bg-gray-800/50" />,
    ssr: false,
});

const StockAnalysisDashboard = dynamic(() => import('./StockAnalysisDashboard'), {
    loading: () => <TabSkeleton />,
    ssr: false,
});

const StockNews = dynamic(() => import('./StockNews'), {
    loading: () => <TabSkeleton />,
    ssr: false,
});

function TabSkeleton() {
    return (
        <div className="space-y-4">
            <Skeleton className="h-[200px] w-full rounded-lg bg-gray-800/50" />
            <Skeleton className="h-[300px] w-full rounded-lg bg-gray-800/50" />
        </div>
    );
}

interface StockPageLayoutProps {
    symbol: string;
    companyName: string;
    currentPrice: number;
}

export default function StockPageLayout({
    symbol,
    companyName,
    currentPrice,
}: StockPageLayoutProps) {
    const [activeTab, setActiveTab] = useState<StockTab>('resumen');
    const scriptUrl = 'https://s3.tradingview.com/external-embedding/embed-widget-';
    const upperSymbol = symbol.toUpperCase();

    return (
        <div className="flex h-[calc(100vh-180px)] overflow-hidden">
            {/* Sidebar */}
            <StockSidebar
                activeTab={activeTab}
                onTabChange={setActiveTab}
                symbol={upperSymbol}
                className="shrink-0 hidden md:flex"
            />

            {/* Main Content Area */}
            <main className="flex-1 overflow-y-auto p-6">
                {/* Mobile Tab Selector */}
                <div className="md:hidden mb-4 overflow-x-auto">
                    <div className="flex gap-2 pb-2">
                        {(['resumen', 'valoracion', 'calidad', 'fundamentales', 'analisis', 'noticias'] as StockTab[]).map((tab) => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`px-4 py-2 rounded-full text-sm whitespace-nowrap transition-colors ${activeTab === tab
                                        ? 'bg-blue-600 text-white'
                                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                                    }`}
                            >
                                {tab.charAt(0).toUpperCase() + tab.slice(1)}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Tab Content - Only renders active tab */}
                <div className="space-y-6">
                    {activeTab === 'resumen' && (
                        <ResumenTab
                            symbol={upperSymbol}
                            scriptUrl={scriptUrl}
                        />
                    )}

                    {activeTab === 'valoracion' && (
                        <ValoracionTab
                            symbol={upperSymbol}
                            currentPrice={currentPrice}
                        />
                    )}

                    {activeTab === 'calidad' && (
                        <CalidadTab symbol={upperSymbol} />
                    )}

                    {activeTab === 'fundamentales' && (
                        <FundamentalesTab symbol={upperSymbol} />
                    )}

                    {activeTab === 'analisis' && (
                        <AnalisisTab
                            symbol={upperSymbol}
                            companyName={companyName}
                            currentPrice={currentPrice}
                        />
                    )}

                    {activeTab === 'noticias' && (
                        <NoticiasTab symbol={upperSymbol} />
                    )}
                </div>
            </main>
        </div>
    );
}

// ============================================================================
// TAB CONTENT COMPONENTS
// ============================================================================

function ResumenTab({ symbol, scriptUrl }: { symbol: string; scriptUrl: string }) {
    return (
        <div className="space-y-6">
            {/* Symbol Info */}
            <div className="min-h-[170px]">
                <TradingViewWidget
                    scriptUrl={`${scriptUrl}symbol-info.js`}
                    config={SYMBOL_INFO_WIDGET_CONFIG(symbol)}
                    height={170}
                />
            </div>

            {/* Main Chart */}
            <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-4 min-h-[500px]">
                <TradingViewWidget
                    scriptUrl={`${scriptUrl}advanced-chart.js`}
                    config={CANDLE_CHART_WIDGET_CONFIG(symbol)}
                    className="custom-chart"
                    height={500}
                />
            </div>

            {/* Technical Analysis */}
            <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                <h2 className="text-lg font-semibold mb-4 text-gray-200">Análisis Técnico</h2>
                <TradingViewWidget
                    scriptUrl={`${scriptUrl}technical-analysis.js`}
                    config={TECHNICAL_ANALYSIS_WIDGET_CONFIG(symbol)}
                    height={400}
                />
            </div>
        </div>
    );
}

function ValoracionTab({ symbol, currentPrice }: { symbol: string; currentPrice: number }) {
    return (
        <div className="space-y-6">
            <h2 className="text-xl font-semibold text-gray-100">Valoración</h2>
            <StockValuation symbol={symbol} currentPrice={currentPrice} />
        </div>
    );
}

function CalidadTab({ symbol }: { symbol: string }) {
    return (
        <div className="space-y-6">
            <h2 className="text-xl font-semibold text-gray-100">Calidad y Salud Financiera</h2>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <HealthScore symbol={symbol} />
                <StockFinancials symbol={symbol} />
            </div>
        </div>
    );
}

function FundamentalesTab({ symbol }: { symbol: string }) {
    return (
        <div className="space-y-6">
            <h2 className="text-xl font-semibold text-gray-100">Fundamentales</h2>
            <StockFundamentals symbol={symbol} />
        </div>
    );
}

function AnalisisTab({
    symbol,
    companyName,
    currentPrice
}: {
    symbol: string;
    companyName: string;
    currentPrice: number;
}) {
    return (
        <div className="space-y-6">
            <h2 className="text-xl font-semibold text-gray-100">Análisis Avanzado</h2>
            <StockAnalysisDashboard
                symbol={symbol}
                companyName={companyName}
                currentPrice={currentPrice}
            />
        </div>
    );
}

function NoticiasTab({ symbol }: { symbol: string }) {
    return (
        <div className="space-y-6">
            <h2 className="text-xl font-semibold text-gray-100">Noticias</h2>
            <StockNews symbol={symbol} />
        </div>
    );
}

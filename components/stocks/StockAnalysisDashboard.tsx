'use client';

import { useEffect, useState } from 'react';
import { getStockFinancialData } from "@/lib/actions/finnhub.actions";
import { Skeleton } from "@/components/ui/skeleton";
import { Loader2 } from 'lucide-react';
import dynamic from 'next/dynamic';

// Lazy load heavy child components
const AIChecklistSection = dynamic(() => import("@/components/stocks/AIChecklistSection"), {
    loading: () => <Skeleton className="h-[200px] w-full rounded-lg bg-gray-800/50" />,
    ssr: false,
});
const PatternAnalysisSection = dynamic(() => import("@/components/stocks/PatternAnalysisSection"), {
    loading: () => <Skeleton className="h-[400px] w-full rounded-lg bg-gray-800/50" />,
    ssr: false,
});
const AlternativesSection = dynamic(() => import("@/components/stocks/AlternativesSection"), {
    loading: () => <Skeleton className="h-[300px] w-full rounded-lg bg-gray-800/50" />,
    ssr: false,
});
const AnalysisWrapper = dynamic(() => import("@/components/stocks/AnalysisWrapper"), {
    loading: () => <Skeleton className="h-[600px] w-full rounded-lg bg-gray-800/50" />,
    ssr: false,
});

interface StockAnalysisDashboardProps {
    symbol: string;
    companyName: string;
    currentPrice: number;
}

export default function StockAnalysisDashboard({
    symbol,
    companyName,
    currentPrice
}: StockAnalysisDashboardProps) {
    const [financialData, setFinancialData] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    useEffect(() => {
        async function fetchData() {
            try {
                setLoading(true);
                setError(false);
                const data = await getStockFinancialData(symbol);
                setFinancialData(data);
            } catch (err) {
                console.error('Error fetching financial data:', err);
                setError(true);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, [symbol]);

    if (loading) {
        return (
            <div className="flex flex-col gap-6 w-full">
                <div className="flex items-center gap-2 text-gray-400">
                    <Loader2 className="h-5 w-5 animate-spin" />
                    <span>Cargando análisis avanzado...</span>
                </div>
                <Skeleton className="h-[200px] w-full rounded-lg bg-gray-800/50" />
                <Skeleton className="h-[400px] w-full rounded-lg bg-gray-800/50" />
                <Skeleton className="h-[300px] w-full rounded-lg bg-gray-800/50" />
            </div>
        );
    }

    if (error || !financialData) {
        return (
            <div className="p-4 rounded-lg bg-red-900/20 border border-red-800 text-red-200">
                No se pudieron cargar los datos financieros completos para el análisis.
            </div>
        );
    }

    const livePrice = financialData.quote?.c || currentPrice;
    const upperSymbol = symbol.toUpperCase();
    const sector = (financialData.profile as any)?.finnhubIndustry || (financialData.profile as any)?.industry || '';

    return (
        <div className="flex flex-col gap-6 w-full">
            {/* AI Checklist Section - Full Width */}
            <section className="w-full">
                <AIChecklistSection
                    symbol={upperSymbol}
                    companyName={companyName}
                    financialData={financialData}
                    currentPrice={livePrice}
                />
            </section>

            {/* Pattern Analysis Section - Full Width */}
            <section className="w-full">
                <PatternAnalysisSection
                    symbol={upperSymbol}
                    companyName={companyName}
                    financialData={financialData}
                    currentPrice={livePrice}
                />
            </section>

            {/* Alternatives Section - Full Width */}
            <section className="w-full">
                <AlternativesSection
                    symbol={upperSymbol}
                    companyName={companyName}
                    sector={sector}
                    financialData={financialData}
                    currentPrice={livePrice}
                />
            </section>

            {/* Analysis Section - Full Width */}
            <section className="w-full">
                <AnalysisWrapper
                    symbol={upperSymbol}
                    companyName={companyName}
                    currentPrice={livePrice}
                />
            </section>
        </div>
    );
}


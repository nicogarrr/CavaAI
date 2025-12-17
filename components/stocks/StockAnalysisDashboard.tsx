import { Suspense } from 'react';
import { getStockFinancialData } from "@/lib/actions/finnhub.actions";
import AIChecklistSection from "@/components/stocks/AIChecklistSection";
import PatternAnalysisSection from "@/components/stocks/PatternAnalysisSection";
import AlternativesSection from "@/components/stocks/AlternativesSection";
import AnalysisWrapper from "@/components/stocks/AnalysisWrapper";

interface StockAnalysisDashboardProps {
    symbol: string;
    companyName: string;
    currentPrice: number;
    // We pass basic info that we already have to avoid refetching if possible, 
    // but the heavy lifting is done here.
}

export default async function StockAnalysisDashboard({
    symbol,
    companyName,
    currentPrice
}: StockAnalysisDashboardProps) {
    // This is the heavy fetch that we want to stream
    const financialData = await getStockFinancialData(symbol);

    if (!financialData) {
        return (
            <div className="p-4 rounded-lg bg-red-900/20 border border-red-800 text-red-200">
                No se pudieron cargar los datos financieros completos para el análisis.
            </div>
        );
    }

    // Refresh currentPrice from financialData if available (more defined) 
    // or keep the one passed from prop (which comes from quote)
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

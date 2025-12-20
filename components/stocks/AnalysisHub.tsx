'use client';

import { useState } from 'react';
import { BarChart3, CheckCircle, TrendingUp, GitCompare, Brain, Loader2 } from 'lucide-react';
import dynamic from 'next/dynamic';
import { Skeleton } from '@/components/ui/skeleton';

// Lazy load tab content components
const VisualThesis = dynamic(() => import('@/components/stocks/VisualThesis'), {
    loading: () => <Skeleton className="h-[500px] w-full rounded-lg bg-gray-800/50" />,
    ssr: false,
});
const AIChecklistSection = dynamic(() => import('@/components/stocks/AIChecklistSection'), {
    loading: () => <Skeleton className="h-[400px] w-full rounded-lg bg-gray-800/50" />,
    ssr: false,
});
const PatternAnalysisSection = dynamic(() => import('@/components/stocks/PatternAnalysisSection'), {
    loading: () => <Skeleton className="h-[400px] w-full rounded-lg bg-gray-800/50" />,
    ssr: false,
});
const AlternativesSection = dynamic(() => import('@/components/stocks/AlternativesSection'), {
    loading: () => <Skeleton className="h-[400px] w-full rounded-lg bg-gray-800/50" />,
    ssr: false,
});

interface AnalysisHubProps {
    symbol: string;
    companyName: string;
    currentPrice: number;
    financialData: any;
    sector: string;
}

type TabType = 'dcf' | 'checklist' | 'technical' | 'competitors';

const TABS: { id: TabType; label: string; icon: React.ReactNode; description: string }[] = [
    { id: 'dcf', label: 'DCF Visual', icon: <BarChart3 className="h-4 w-4" />, description: 'Valoración por descuento de flujos' },
    { id: 'checklist', label: 'Checklist', icon: <CheckCircle className="h-4 w-4" />, description: '15 preguntas value investing' },
    { id: 'technical', label: 'Técnico', icon: <TrendingUp className="h-4 w-4" />, description: 'Patrones y soportes/resistencias' },
    { id: 'competitors', label: 'Competidores', icon: <GitCompare className="h-4 w-4" />, description: 'Comparación con el sector' },
];

export default function AnalysisHub({
    symbol,
    companyName,
    currentPrice,
    financialData,
    sector
}: AnalysisHubProps) {
    const [activeTab, setActiveTab] = useState<TabType>('dcf');

    return (
        <div className="space-y-4">
            {/* Hub Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
                        <Brain className="h-5 w-5 text-white" />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-white">Hub de Análisis</h2>
                        <p className="text-sm text-gray-400">{symbol} • {companyName}</p>
                    </div>
                </div>
            </div>

            {/* Tabs Navigation */}
            <div className="bg-[#0a0a0a] border border-gray-800 rounded-xl p-1 flex gap-1">
                {TABS.map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-lg transition-all duration-200 ${activeTab === tab.id
                                ? 'bg-gradient-to-r from-indigo-500/20 to-purple-500/20 border border-indigo-500/50 text-white'
                                : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
                            }`}
                    >
                        {tab.icon}
                        <span className="hidden sm:inline text-sm font-medium">{tab.label}</span>
                    </button>
                ))}
            </div>

            {/* Active Tab Description */}
            <div className="flex items-center justify-between px-2">
                <p className="text-xs text-gray-500">
                    {TABS.find(t => t.id === activeTab)?.description}
                </p>
                <span className="text-[10px] text-indigo-400 bg-indigo-500/10 px-2 py-1 rounded">
                    Datos en vivo • FMP + Finnhub
                </span>
            </div>

            {/* Tab Content */}
            <div className="min-h-[500px]">
                {activeTab === 'dcf' && (
                    <VisualThesis
                        symbol={symbol}
                        companyName={companyName}
                        currentPrice={currentPrice}
                    />
                )}

                {activeTab === 'checklist' && (
                    <AIChecklistSection
                        symbol={symbol}
                        companyName={companyName}
                        financialData={financialData}
                        currentPrice={currentPrice}
                    />
                )}

                {activeTab === 'technical' && (
                    <PatternAnalysisSection
                        symbol={symbol}
                        companyName={companyName}
                        financialData={financialData}
                        currentPrice={currentPrice}
                    />
                )}

                {activeTab === 'competitors' && (
                    <AlternativesSection
                        symbol={symbol}
                        companyName={companyName}
                        sector={sector}
                        financialData={financialData}
                        currentPrice={currentPrice}
                    />
                )}
            </div>
        </div>
    );
}

'use client';

import { useState } from 'react';
import CombinedAnalysis from './CombinedAnalysis';
import AnalysisGenerator from './AnalysisGenerator';

interface AnalysisWrapperProps {
    symbol: string;
    companyName: string;
    currentPrice: number;
}

export default function AnalysisWrapper({ symbol, companyName, currentPrice }: AnalysisWrapperProps) {
    const [analysis, setAnalysis] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    const handleAnalysisGenerated = (generatedAnalysis: string | null, loading: boolean) => {
        setAnalysis(generatedAnalysis);
        setIsLoading(loading);
    };

    return (
        <div className="flex flex-col gap-6">
            <AnalysisGenerator
                symbol={symbol}
                companyName={companyName}
                currentPrice={currentPrice}
                onAnalysisGenerated={handleAnalysisGenerated}
                isLoading={isLoading}
            />
            {analysis && (
                <CombinedAnalysis analysis={analysis} isLoading={isLoading} />
            )}
        </div>
    );
}


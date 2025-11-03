'use client';

import AnalysisGenerator from './AnalysisGenerator';

interface AnalysisWrapperProps {
    symbol: string;
    companyName: string;
    currentPrice: number;
}

export default function AnalysisWrapper({ symbol, companyName, currentPrice }: AnalysisWrapperProps) {
    return (
        <AnalysisGenerator
            symbol={symbol}
            companyName={companyName}
            currentPrice={currentPrice}
        />
    );
}


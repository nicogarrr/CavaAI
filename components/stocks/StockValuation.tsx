'use client';

import { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Loader2, Target, TrendingUp, TrendingDown, Building2, Percent, DollarSign } from 'lucide-react';
import { getValuationData, type RatiosTTM, type DCFData, type EnterpriseValueData } from '@/lib/actions/fmp.actions';

interface StockValuationProps {
    symbol: string;
    currentPrice?: number;
}

const formatNumber = (num: number | undefined | null, decimals = 2) => {
    if (num === undefined || num === null || isNaN(num)) return 'N/A';
    return num.toLocaleString('en-US', { maximumFractionDigits: decimals });
};

const formatPercent = (num: number | undefined | null) => {
    if (num === undefined || num === null || isNaN(num)) return 'N/A';
    return `${(num * 100).toFixed(1)}%`;
};

const formatBillions = (num: number | undefined | null) => {
    if (num === undefined || num === null || isNaN(num)) return 'N/A';
    if (Math.abs(num) >= 1e12) return `$${(num / 1e12).toFixed(1)}T`;
    if (Math.abs(num) >= 1e9) return `$${(num / 1e9).toFixed(1)}B`;
    if (Math.abs(num) >= 1e6) return `$${(num / 1e6).toFixed(1)}M`;
    return `$${num.toFixed(0)}`;
};

export default function StockValuation({ symbol, currentPrice }: StockValuationProps) {
    const [ratios, setRatios] = useState<RatiosTTM | null>(null);
    const [dcf, setDcf] = useState<DCFData | null>(null);
    const [ev, setEv] = useState<EnterpriseValueData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchData() {
            try {
                setLoading(true);
                const data = await getValuationData(symbol);

                // Extract first item from arrays
                if (data.ratios?.ratios?.[0]) setRatios(data.ratios.ratios[0]);
                if (data.dcf?.dcf?.[0]) setDcf(data.dcf.dcf[0]);
                if (data.ev?.enterpriseValue?.[0]) setEv(data.ev.enterpriseValue[0]);
            } catch (err) {
                setError('Error loading valuation data');
                console.error(err);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, [symbol]);

    if (loading) {
        return (
            <Card className="bg-gray-800/50 border-gray-700">
                <CardContent className="flex items-center justify-center h-[300px]">
                    <Loader2 className="h-8 w-8 animate-spin text-teal-400" />
                </CardContent>
            </Card>
        );
    }

    if (error || (!ratios && !dcf && !ev)) {
        return (
            <Card className="bg-gray-800/50 border-gray-700">
                <CardContent className="flex items-center justify-center h-[300px]">
                    <p className="text-gray-400">{error || 'No valuation data available'}</p>
                </CardContent>
            </Card>
        );
    }

    // Calculate upside/downside for DCF
    const stockPrice = dcf?.stockPrice || currentPrice || 0;
    const intrinsicValue = dcf?.dcf || 0;
    const upside = stockPrice > 0 ? ((intrinsicValue - stockPrice) / stockPrice) * 100 : 0;
    const isUndervalued = upside > 0;

    return (
        <Card className="bg-gray-800/50 border-gray-700">
            <CardHeader className="pb-2">
                <CardTitle className="text-gray-100 flex items-center gap-2">
                    <Target className="h-5 w-5 text-purple-400" />
                    Métricas de Valoración
                    <Badge variant="outline" className="ml-2 text-xs border-purple-500/30 text-purple-400">
                        FMP TTM
                    </Badge>
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">

                {/* DCF Valuation Card */}
                {dcf && (
                    <div className="bg-gradient-to-br from-gray-900/60 to-gray-800/40 rounded-xl p-4 border border-gray-700">
                        <div className="flex items-center gap-2 mb-3">
                            <DollarSign className="h-4 w-4 text-amber-400" />
                            <span className="text-sm font-semibold text-gray-200">DCF Intrinsic Value</span>
                        </div>

                        <div className="grid grid-cols-3 gap-4">
                            <div className="text-center">
                                <p className="text-xs text-gray-500 mb-1">Stock Price</p>
                                <p className="text-xl font-bold text-gray-100">${formatNumber(stockPrice)}</p>
                            </div>
                            <div className="text-center">
                                <p className="text-xs text-gray-500 mb-1">Intrinsic Value</p>
                                <p className="text-xl font-bold text-amber-400">${formatNumber(intrinsicValue)}</p>
                            </div>
                            <div className="text-center">
                                <p className="text-xs text-gray-500 mb-1">Upside/Downside</p>
                                <div className="flex items-center justify-center gap-1">
                                    {isUndervalued ? (
                                        <TrendingUp className="h-4 w-4 text-green-400" />
                                    ) : (
                                        <TrendingDown className="h-4 w-4 text-red-400" />
                                    )}
                                    <p className={`text-xl font-bold ${isUndervalued ? 'text-green-400' : 'text-red-400'}`}>
                                        {upside > 0 ? '+' : ''}{formatNumber(upside)}%
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Visual Bar */}
                        <div className="mt-4">
                            <div className="relative h-3 bg-gray-700 rounded-full overflow-hidden">
                                <div
                                    className={`absolute h-full ${isUndervalued ? 'bg-gradient-to-r from-green-600 to-green-400' : 'bg-gradient-to-r from-red-600 to-red-400'}`}
                                    style={{ width: `${Math.min(100, Math.abs(upside))}%` }}
                                />
                            </div>
                            <div className="flex justify-between mt-1 text-[10px] text-gray-500">
                                <span>Overvalued</span>
                                <span>Fair Value</span>
                                <span>Undervalued</span>
                            </div>
                        </div>
                    </div>
                )}

                {/* Ratios TTM Grid */}
                {ratios && (
                    <div className="space-y-3">
                        <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
                            <Percent className="h-3 w-3" />
                            Ratios TTM
                        </h4>

                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                            <MetricCard
                                label="P/E Ratio"
                                value={formatNumber(ratios.peRatioTTM)}
                                suffix="x"
                                color={ratios.peRatioTTM < 25 ? 'green' : ratios.peRatioTTM < 40 ? 'yellow' : 'red'}
                            />
                            <MetricCard
                                label="PEG Ratio"
                                value={formatNumber(ratios.pegRatioTTM)}
                                suffix="x"
                                color={ratios.pegRatioTTM < 1 ? 'green' : ratios.pegRatioTTM < 2 ? 'yellow' : 'red'}
                            />
                            <MetricCard
                                label="P/S Ratio"
                                value={formatNumber(ratios.priceToSalesRatioTTM)}
                                suffix="x"
                                color={ratios.priceToSalesRatioTTM < 5 ? 'green' : ratios.priceToSalesRatioTTM < 10 ? 'yellow' : 'red'}
                            />
                            <MetricCard
                                label="P/B Ratio"
                                value={formatNumber(ratios.priceToBookRatioTTM)}
                                suffix="x"
                                color={ratios.priceToBookRatioTTM < 3 ? 'green' : ratios.priceToBookRatioTTM < 5 ? 'yellow' : 'red'}
                            />
                            <MetricCard
                                label="ROE"
                                value={formatNumber(ratios.returnOnEquityTTM * 100)}
                                suffix="%"
                                color={ratios.returnOnEquityTTM > 0.15 ? 'green' : ratios.returnOnEquityTTM > 0.10 ? 'yellow' : 'red'}
                            />
                            <MetricCard
                                label="ROIC"
                                value={formatNumber(ratios.returnOnCapitalEmployedTTM * 100)}
                                suffix="%"
                                color={ratios.returnOnCapitalEmployedTTM > 0.12 ? 'green' : ratios.returnOnCapitalEmployedTTM > 0.08 ? 'yellow' : 'red'}
                            />
                        </div>
                    </div>
                )}

                {/* Enterprise Value Metrics */}
                {ev && (
                    <div className="space-y-3">
                        <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
                            <Building2 className="h-3 w-3" />
                            Enterprise Value
                        </h4>

                        <div className="grid grid-cols-2 gap-3">
                            <div className="bg-gray-900/40 p-3 rounded-lg border border-gray-700">
                                <p className="text-xs text-gray-500 mb-1">Market Cap</p>
                                <p className="text-lg font-bold text-gray-100">{formatBillions(ev.marketCapitalization)}</p>
                            </div>
                            <div className="bg-gray-900/40 p-3 rounded-lg border border-gray-700">
                                <p className="text-xs text-gray-500 mb-1">Enterprise Value</p>
                                <p className="text-lg font-bold text-purple-400">{formatBillions(ev.enterpriseValue)}</p>
                            </div>
                            <div className="bg-gray-900/40 p-3 rounded-lg border border-gray-700">
                                <p className="text-xs text-gray-500 mb-1">Total Debt</p>
                                <p className="text-lg font-bold text-red-400">{formatBillions(ev.addTotalDebt)}</p>
                            </div>
                            <div className="bg-gray-900/40 p-3 rounded-lg border border-gray-700">
                                <p className="text-xs text-gray-500 mb-1">Cash & Equivalents</p>
                                <p className="text-lg font-bold text-green-400">{formatBillions(Math.abs(ev.minusCashAndCashEquivalents))}</p>
                            </div>
                        </div>
                    </div>
                )}

                {/* Profitability Margins from Ratios */}
                {ratios && (
                    <div className="space-y-3">
                        <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                            Profitability Margins
                        </h4>

                        <div className="space-y-2">
                            <MarginBar label="Gross Margin" value={ratios.grossProfitMarginTTM} />
                            <MarginBar label="Operating Margin" value={ratios.operatingProfitMarginTTM} />
                            <MarginBar label="Net Margin" value={ratios.netProfitMarginTTM} />
                        </div>
                    </div>
                )}

            </CardContent>
        </Card>
    );
}

// Helper Components
function MetricCard({ label, value, suffix, color }: { label: string; value: string; suffix?: string; color: 'green' | 'yellow' | 'red' }) {
    const colorClasses = {
        green: 'text-green-400 border-green-800/50',
        yellow: 'text-yellow-400 border-yellow-800/50',
        red: 'text-red-400 border-red-800/50',
    };

    return (
        <div className={`bg-gray-900/40 p-3 rounded-lg border ${colorClasses[color]} hover:border-opacity-100 transition-colors`}>
            <p className="text-xs text-gray-500 mb-1">{label}</p>
            <p className={`text-lg font-bold ${colorClasses[color].split(' ')[0]}`}>
                {value}{suffix}
            </p>
        </div>
    );
}

function MarginBar({ label, value }: { label: string; value: number }) {
    const percent = (value || 0) * 100;
    const displayValue = percent.toFixed(1);

    return (
        <div className="space-y-1">
            <div className="flex justify-between text-xs">
                <span className="text-gray-300">{label}</span>
                <span className="font-mono text-gray-100">{displayValue}%</span>
            </div>
            <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                <div
                    className={`h-full rounded-full transition-all ${percent >= 20 ? 'bg-green-500' : percent >= 10 ? 'bg-yellow-500' : 'bg-red-500'
                        }`}
                    style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
                />
            </div>
        </div>
    );
}

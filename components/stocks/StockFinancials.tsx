import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { DollarSign, Percent, Activity, TrendingUp } from 'lucide-react';
import { getStockFinancialData } from "@/lib/actions/finnhub.actions";

interface StockFinancialsProps {
    symbol: string;
}

export default async function StockFinancials({ symbol }: StockFinancialsProps) {
    const data = await getStockFinancialData(symbol);
    const metrics = data?.metrics?.metric || data?.metrics || {};

    // Helper to format large numbers
    const formatNumber = (num: number | undefined | null, suffix = '') => {
        if (num === undefined || num === null) return 'N/A';
        return num.toLocaleString('en-US', { maximumFractionDigits: 2 }) + suffix;
    };

    // Color helpers
    const getScoreColor = (score: number, threshold = 50) => score >= threshold ? 'text-green-400' : 'text-red-400';
    const getProgressColor = (val: number) => val >= 20 ? 'bg-green-500' : val >= 10 ? 'bg-yellow-500' : 'bg-red-500';

    // Data Extraction - Add fallbacks
    const pe = metrics.peTTM || metrics.peBasicExclExtraTTM || metrics.peExclExtraTTM || null;
    const eps = metrics.epsTTM || metrics.epsBasicExclExtraTTM || metrics.epsExclExtraTTM || 0;
    const marketCap = metrics.marketCapitalization || 0;
    const dividendYield = metrics.dividendYieldIndicatedAnnual || metrics.dividendYield || 0;

    // Margins
    const grossMargin = metrics.grossMarginTTM || metrics.grossMargin5Y || 0;
    const operatingMargin = metrics.operatingMarginTTM || metrics.operatingMargin5Y || 0;
    const netMargin = metrics.netProfitMarginTTM || metrics.netProfitMargin5Y || 0;

    // Health - Add Annual/Quarterly fallbacks
    const currentRatio = metrics.currentRatioTTM || metrics.currentRatioQuarterly || metrics.currentRatioAnnual || null;
    const debtToEquity = metrics.totalDebtToEquityTTM || metrics.totalDebtToEquityQuarterly || metrics.totalDebtToEquityAnnual || null;

    return (
        <Card className="bg-gray-800/50 border-gray-700">
            <CardHeader>
                <CardTitle className="text-gray-100 flex items-center gap-2">
                    <Activity className="h-5 w-5 text-teal-400" />
                    Estados Financieros
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">

                {/* 1. KPIs Cards */}
                <div className="grid grid-cols-2 gap-3">
                    <div className="bg-gray-900/40 p-3 rounded-lg border border-gray-700 hover:border-teal-500/30 transition-colors">
                        <p className="text-xs text-gray-500 mb-1">Market Cap</p>
                        <p className="text-lg font-bold text-gray-100">${formatNumber(marketCap)}M</p>
                    </div>
                    <div className="bg-gray-900/40 p-3 rounded-lg border border-gray-700 hover:border-teal-500/30 transition-colors">
                        <p className="text-xs text-gray-500 mb-1">P/E Ratio (TTM)</p>
                        <p className="text-lg font-bold text-teal-400">{formatNumber(pe)}x</p>
                    </div>
                    <div className="bg-gray-900/40 p-3 rounded-lg border border-gray-700 hover:border-teal-500/30 transition-colors">
                        <p className="text-xs text-gray-500 mb-1">EPS (TTM)</p>
                        <p className="text-lg font-bold text-gray-100">${formatNumber(eps)}</p>
                    </div>
                    <div className="bg-gray-900/40 p-3 rounded-lg border border-gray-700 hover:border-teal-500/30 transition-colors">
                        <p className="text-xs text-gray-500 mb-1">Div. Yield</p>
                        <p className="text-lg font-bold text-green-400">{formatNumber(dividendYield)}%</p>
                    </div>
                </div>

                {/* 2. Visual Margins */}
                <div className="space-y-3 pt-2">
                    <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Márgenes de Rentabilidad</h4>

                    <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                            <span className="text-gray-300">Margen Bruto</span>
                            <span className="font-mono text-gray-100">{formatNumber(grossMargin)}%</span>
                        </div>
                        <Progress value={Math.min(100, grossMargin)} className="h-2 bg-gray-700" indicatorClassName="bg-blue-500" />
                    </div>

                    <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                            <span className="text-gray-300">Margen Operativo</span>
                            <span className="font-mono text-gray-100">{formatNumber(operatingMargin)}%</span>
                        </div>
                        <Progress value={Math.min(100, operatingMargin)} className="h-2 bg-gray-700" indicatorClassName="bg-indigo-500" />
                    </div>

                    <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                            <span className="text-gray-300">Margen Neto</span>
                            <span className="font-mono text-gray-100">{formatNumber(netMargin)}%</span>
                        </div>
                        <Progress value={Math.min(100, netMargin)} className="h-2 bg-gray-700" indicatorClassName={getProgressColor(netMargin)} />
                    </div>
                </div>

                {/* 3. Financial Health Helpers */}
                <div className="space-y-3 pt-2">
                    <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Salud Financiera</h4>
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-1">
                            <div className="flex justify-between text-xs">
                                <span className="text-gray-300">Current Ratio</span>
                                <Badge variant="outline" className={`text-xs ${currentRatio >= 1.5 ? 'border-green-800 text-green-400' : currentRatio >= 1 ? 'border-yellow-800 text-yellow-400' : 'border-red-800 text-red-400'}`}>
                                    {formatNumber(currentRatio)}
                                </Badge>
                            </div>
                            <p className="text-[10px] text-gray-500">Liquidez a corto plazo ({'>'}1.5 ideal)</p>
                        </div>
                        <div className="space-y-1">
                            <div className="flex justify-between text-xs">
                                <span className="text-gray-300">Debt to Equity</span>
                                <Badge variant="outline" className={`text-xs ${debtToEquity <= 50 ? 'border-green-800 text-green-400' : debtToEquity <= 100 ? 'border-yellow-800 text-yellow-400' : 'border-red-800 text-red-400'}`}>
                                    {formatNumber(debtToEquity)}%
                                </Badge>
                            </div>
                            <p className="text-[10px] text-gray-500">Deuda vs Patrimonio ({'<'}100% ideal)</p>
                        </div>
                    </div>
                </div>

            </CardContent>
        </Card>
    );
}

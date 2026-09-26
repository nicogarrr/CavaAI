'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Shield, TrendingUp, CircleDollarSign, Coins, Percent } from 'lucide-react';
import { formatNumber, formatPercent } from '@/lib/format';
import { t } from '@/lib/i18n/t';

interface PortfolioScoresProps {
    scores: {
        quality: number | null;
        growth: number | null;
        value: number | null;
        dividend: number | null;
        cagr3y: number | null;
    };
}

export default function PortfolioScores({ scores }: PortfolioScoresProps) {
    const scoreItems = [
        { label: t('portfolio.scores.quality'), value: scores.quality, icon: Shield, color: 'text-purple-400' },
        { label: t('portfolio.scores.growth'), value: scores.growth, icon: TrendingUp, color: 'text-blue-400' },
        { label: t('portfolio.scores.value'), value: scores.value, icon: CircleDollarSign, color: 'text-green-400' },
        { label: t('portfolio.scores.dividend'), value: scores.dividend, icon: Coins, color: 'text-yellow-400' },
        { label: 'CAGR 3Y', value: scores.cagr3y, icon: Percent, color: 'text-teal-400', isPercent: true },
    ];
    const missing = scoreItems.filter((item) => item.value == null).map((item) => item.label);

    return (
        <Card className="bg-gray-800/50 border-gray-700">
            <CardHeader className="pb-2">
                <CardTitle className="text-lg text-gray-100">Puntuaciones</CardTitle>
            </CardHeader>
            <CardContent>
                <div className="grid grid-cols-5 gap-4">
                    {scoreItems.map((item) => (
                        <div key={item.label} className="text-center p-3 bg-gray-900/50 rounded-lg">
                            <item.icon className={`h-6 w-6 mx-auto mb-2 ${item.color}`} />
                            {item.value == null ? (
                                <>
                                    <div
                                        className="text-2xl font-bold text-gray-500"
                                        title="No hay datos suficientes para calcular esta puntuaci��n"
                                    >
                                        &mdash;
                                    </div>
                                    <div className="text-[10px] uppercase tracking-wide text-gray-500">
                                        sin datos
                                    </div>
                                </>
                            ) : (
                                <>
                                    <div className="text-2xl font-bold text-gray-100">
                                        {item.isPercent
                                            ? formatPercent(item.value, { fromRatio: false, digits: 2 })
                                            : formatNumber(item.value, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </div>
                                    <div className="text-xs text-gray-400">{item.label}</div>
                                </>
                            )}
                        </div>
                    ))}
                </div>
                {missing.length > 0 && (
                    <p className="mt-3 text-xs text-gray-500">
                        Sin datos para: {missing.join(', ')}. Una puntuaci��n sin datos no es un 0.
                    </p>
                )}
            </CardContent>
        </Card>
    );
}

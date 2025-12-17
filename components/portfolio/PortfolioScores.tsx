'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Shield, TrendingUp, CircleDollarSign, Coins, Percent } from 'lucide-react';

interface PortfolioScoresProps {
    scores: {
        quality: number;
        growth: number;
        value: number;
        dividend: number;
        cagr3y: number;
    };
}

export default function PortfolioScores({ scores }: PortfolioScoresProps) {
    const scoreItems = [
        { label: 'Quality', value: scores.quality, icon: Shield, color: 'text-purple-400' },
        { label: 'Growth', value: scores.growth, icon: TrendingUp, color: 'text-blue-400' },
        { label: 'Value', value: scores.value, icon: CircleDollarSign, color: 'text-green-400' },
        { label: 'Dividend', value: scores.dividend, icon: Coins, color: 'text-yellow-400' },
        { label: 'CAGR 3Y', value: scores.cagr3y, icon: Percent, color: 'text-teal-400', isPercent: true },
    ];

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
                            <div className="text-2xl font-bold text-gray-100">
                                {item.isPercent ? `${item.value.toFixed(2)}%` : item.value.toFixed(2)}
                            </div>
                            <div className="text-xs text-gray-400">{item.label}</div>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}

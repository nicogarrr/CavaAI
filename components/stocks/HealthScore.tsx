'use client';

import { useEffect, useState } from 'react';
import { getStockHealthScore } from '@/lib/actions/healthScore.actions';
import { Card } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { TrendingUp, TrendingDown, Shield, DollarSign, Activity, Loader2 } from 'lucide-react';
import { useStockCache } from '@/lib/cache/useSessionCache';

interface HealthScoreProps {
    symbol: string;
}

interface HealthScoreData {
    score: number;
    grade: string;
    breakdown: {
        profitability: number;
        growth: number;
        stability: number;
        efficiency: number;
        valuation: number;
    };
    strengths: string[];
    weaknesses: string[];
}

const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-400';
    if (score >= 70) return 'text-teal-400';
    if (score >= 60) return 'text-yellow-400';
    if (score >= 50) return 'text-orange-400';
    return 'text-red-400';
};

const getGradeColor = (grade: string) => {
    if (grade.startsWith('A')) return 'bg-green-500';
    if (grade.startsWith('B')) return 'bg-teal-500';
    if (grade.startsWith('C')) return 'bg-yellow-500';
    return 'bg-red-500';
};

export default function HealthScore({ symbol }: HealthScoreProps) {
    // Use session cache to persist data between tab changes (15 min TTL)
    const {
        data: cachedData,
        setData: setCachedData
    } = useStockCache<HealthScoreData | null>(symbol, 'healthscore', { ttlMinutes: 15 });

    const [healthScore, setHealthScore] = useState<HealthScoreData | null>(cachedData ?? null);
    const [loading, setLoading] = useState(!cachedData);
    const [error, setError] = useState(false);

    useEffect(() => {
        // If we have cached data, use it and skip fetch
        if (cachedData) {
            setHealthScore(cachedData);
            setLoading(false);
            return;
        }

        async function fetchData() {
            try {
                setLoading(true);
                setError(false);
                const data = await getStockHealthScore(symbol);
                setHealthScore(data);
                setCachedData(data); // Save to cache
            } catch (err) {
                console.error('Error fetching health score:', err);
                setError(true);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, [symbol, cachedData, setCachedData]);

    if (loading) {
        return (
            <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-lg font-semibold text-gray-200">Health Score</h2>
                    <Loader2 className="h-6 w-6 text-gray-400 animate-spin" />
                </div>
                <div className="space-y-4">
                    <Skeleton className="h-4 w-full bg-gray-700" />
                    <Skeleton className="h-4 w-3/4 bg-gray-700" />
                    <Skeleton className="h-4 w-5/6 bg-gray-700" />
                    <Skeleton className="h-4 w-2/3 bg-gray-700" />
                </div>
            </Card>
        );
    }

    if (error || !healthScore) {
        return (
            <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
                <h2 className="text-lg font-semibold mb-4 text-gray-200">Health Score</h2>
                <p className="text-sm text-gray-500">No hay datos disponibles para calcular el Health Score.</p>
            </Card>
        );
    }

    return (
        <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-lg font-semibold text-gray-200">Health Score</h2>
                <div className="flex items-center gap-3">
                    <span className={`text-4xl font-bold ${getScoreColor(healthScore.score)}`}>
                        {healthScore.score}
                    </span>
                    <span className={`px-3 py-1 rounded-lg text-white font-bold text-lg ${getGradeColor(healthScore.grade)}`}>
                        {healthScore.grade}
                    </span>
                </div>
            </div>

            {/* Breakdown por categorías */}
            <div className="space-y-4 mb-6">
                <div>
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                            <DollarSign className="h-4 w-4 text-gray-400" />
                            <span className="text-sm text-gray-300">Rentabilidad</span>
                        </div>
                        <span className="text-sm font-medium text-gray-300">{healthScore.breakdown.profitability}/100</span>
                    </div>
                    <Progress value={healthScore.breakdown.profitability} className="h-2" />
                </div>

                <div>
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                            <TrendingUp className="h-4 w-4 text-gray-400" />
                            <span className="text-sm text-gray-300">Crecimiento</span>
                        </div>
                        <span className="text-sm font-medium text-gray-300">{healthScore.breakdown.growth}/100</span>
                    </div>
                    <Progress value={healthScore.breakdown.growth} className="h-2" />
                </div>

                <div>
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                            <Shield className="h-4 w-4 text-gray-400" />
                            <span className="text-sm text-gray-300">Estabilidad</span>
                        </div>
                        <span className="text-sm font-medium text-gray-300">{healthScore.breakdown.stability}/100</span>
                    </div>
                    <Progress value={healthScore.breakdown.stability} className="h-2" />
                </div>

                <div>
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                            <Activity className="h-4 w-4 text-gray-400" />
                            <span className="text-sm text-gray-300">Eficiencia</span>
                        </div>
                        <span className="text-sm font-medium text-gray-300">{healthScore.breakdown.efficiency}/100</span>
                    </div>
                    <Progress value={healthScore.breakdown.efficiency} className="h-2" />
                </div>

                <div>
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-gray-300">Valuación</span>
                        <span className="text-sm font-medium text-gray-300">{healthScore.breakdown.valuation}/100</span>
                    </div>
                    <Progress value={healthScore.breakdown.valuation} className="h-2" />
                </div>
            </div>

            {/* Fortalezas y Debilidades */}
            {healthScore.strengths.length > 0 && (
                <div className="mb-4">
                    <h3 className="text-sm font-semibold text-green-400 mb-2 flex items-center gap-2">
                        <TrendingUp className="h-4 w-4" />
                        Fortalezas
                    </h3>
                    <ul className="space-y-1">
                        {healthScore.strengths.map((strength, index) => (
                            <li key={index} className="text-sm text-gray-300 flex items-center gap-2">
                                <span className="text-green-400">✓</span>
                                {strength}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {healthScore.weaknesses.length > 0 && (
                <div>
                    <h3 className="text-sm font-semibold text-red-400 mb-2 flex items-center gap-2">
                        <TrendingDown className="h-4 w-4" />
                        Áreas de Mejora
                    </h3>
                    <ul className="space-y-1">
                        {healthScore.weaknesses.map((weakness, index) => (
                            <li key={index} className="text-sm text-gray-300 flex items-center gap-2">
                                <span className="text-red-400">⚠</span>
                                {weakness}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </Card>
    );
}

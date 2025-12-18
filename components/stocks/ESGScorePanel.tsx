'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Leaf, Users, Shield, Info } from 'lucide-react';

type ESGScore = {
    symbol: string;
    totalESG: number;
    environmentalScore: number;
    socialScore: number;
    governanceScore: number;
    lastRefreshDate: string;
    level: string;
    peersCount: number;
    percentile: number;
};

interface ESGScorePanelProps {
    symbol: string;
}

function getScoreColor(score: number): string {
    if (score >= 70) return 'text-green-500';
    if (score >= 50) return 'text-yellow-500';
    if (score >= 30) return 'text-orange-500';
    return 'text-red-500';
}

function getScoreLabel(score: number): string {
    if (score >= 70) return 'Excelente';
    if (score >= 50) return 'Bueno';
    if (score >= 30) return 'Regular';
    return 'Bajo';
}

function getProgressColor(score: number): string {
    if (score >= 70) return 'bg-green-500';
    if (score >= 50) return 'bg-yellow-500';
    if (score >= 30) return 'bg-orange-500';
    return 'bg-red-500';
}

export default function ESGScorePanel({ symbol }: ESGScorePanelProps) {
    const [esg, setEsg] = useState<ESGScore | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchESG() {
            setLoading(true);
            try {
                const { getESGScores } = await import('@/lib/actions/finnhub.actions');
                const data = await getESGScores(symbol);
                setEsg(data);
                setError(null);
            } catch (err) {
                console.error('Error fetching ESG scores:', err);
                setError('Error al cargar puntuación ESG');
            } finally {
                setLoading(false);
            }
        }
        fetchESG();
    }, [symbol]);

    if (loading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Leaf className="h-5 w-5 text-green-500" />
                        Puntuación ESG
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="space-y-4">
                        <Skeleton className="h-20 w-full" />
                        <Skeleton className="h-8 w-full" />
                        <Skeleton className="h-8 w-full" />
                        <Skeleton className="h-8 w-full" />
                    </div>
                </CardContent>
            </Card>
        );
    }

    if (error || !esg) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Leaf className="h-5 w-5 text-green-500" />
                        Puntuación ESG
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-muted-foreground text-center py-6">
                        {error || `No hay datos ESG disponibles para ${symbol}`}
                    </p>
                </CardContent>
            </Card>
        );
    }

    const scoreItems = [
        {
            label: 'Medioambiental',
            score: esg.environmentalScore,
            icon: Leaf,
            color: 'text-green-500',
            bgColor: 'bg-green-500'
        },
        {
            label: 'Social',
            score: esg.socialScore,
            icon: Users,
            color: 'text-blue-500',
            bgColor: 'bg-blue-500'
        },
        {
            label: 'Gobernanza',
            score: esg.governanceScore,
            icon: Shield,
            color: 'text-purple-500',
            bgColor: 'bg-purple-500'
        },
    ];

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Leaf className="h-5 w-5 text-green-500" />
                    Puntuación ESG
                </CardTitle>
                <CardDescription>
                    Environmental, Social & Governance
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                {/* Total Score */}
                <div className="text-center p-4 rounded-lg bg-gradient-to-br from-green-500/10 to-blue-500/10 border">
                    <div className={`text-4xl font-bold ${getScoreColor(esg.totalESG)}`}>
                        {esg.totalESG.toFixed(1)}
                    </div>
                    <Badge className="mt-2" variant="secondary">
                        {getScoreLabel(esg.totalESG)}
                    </Badge>
                    {esg.percentile > 0 && (
                        <p className="text-xs text-muted-foreground mt-2">
                            Top {100 - esg.percentile}% en su sector
                        </p>
                    )}
                </div>

                {/* Individual Scores */}
                <div className="space-y-4">
                    {scoreItems.map(({ label, score, icon: Icon, color, bgColor }) => (
                        <div key={label} className="space-y-2">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <Icon className={`h-4 w-4 ${color}`} />
                                    <span className="text-sm font-medium">{label}</span>
                                </div>
                                <span className={`text-sm font-bold ${getScoreColor(score)}`}>
                                    {score.toFixed(1)}
                                </span>
                            </div>
                            <div className="h-2 bg-secondary rounded-full overflow-hidden">
                                <div
                                    className={`h-full ${bgColor} transition-all duration-500`}
                                    style={{ width: `${Math.min(score, 100)}%` }}
                                />
                            </div>
                        </div>
                    ))}
                </div>

                {/* Footer Info */}
                <div className="flex items-center gap-2 text-xs text-muted-foreground pt-2 border-t">
                    <Info className="h-3 w-3" />
                    <span>
                        Comparado con {esg.peersCount} empresas similares
                        {esg.lastRefreshDate && ` | Actualizado: ${new Date(esg.lastRefreshDate).toLocaleDateString('es-ES')}`}
                    </span>
                </div>
            </CardContent>
        </Card>
    );
}

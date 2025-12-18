'use client';

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FinancialScore, PeerCompany, getFinancialScores, getStockPeers } from "@/lib/actions/fmp.actions";
import { Gauge, Users, ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";

interface StockValuationProps {
    symbol: string;
}

export default function StockValuation({ symbol }: StockValuationProps) {
    const [scoreData, setScoreData] = useState<FinancialScore | null>(null);
    const [peerData, setPeerData] = useState<PeerCompany | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                const [scores, peers] = await Promise.all([
                    getFinancialScores(symbol),
                    getStockPeers(symbol)
                ]);
                setScoreData(scores);
                setPeerData(peers);
            } catch (error) {
                console.error("Failed to fetch valuation data", error);
            } finally {
                setLoading(false);
            }
        };

        if (symbol) {
            fetchData();
        }
    }, [symbol]);

    // Helpers for Score Colors
    const getAltmanColor = (score: number) => {
        if (score > 3) return "text-green-500";
        if (score > 1.8) return "text-yellow-500";
        return "text-red-500";
    };

    const getPiotroskiColor = (score: number) => {
        if (score >= 7) return "text-green-500"; // Strong
        if (score >= 4) return "text-yellow-500"; // Average
        return "text-red-500"; // Weak
    };

    if (loading) {
        return (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Skeleton className="h-[200px] w-full rounded-lg bg-gray-800/50" />
                <Skeleton className="h-[200px] w-full rounded-lg bg-gray-800/50" />
                <Skeleton className="h-[200px] w-full rounded-lg bg-gray-800/50 col-span-full" />
            </div>
        );
    }

    // Handle peer data safely
    const peerList = peerData?.peersList || [];

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Altman Z-Score */}
                <Card className="bg-gray-900 border-gray-800">
                    <CardHeader>
                        <CardTitle className="text-gray-100 flex items-center gap-2">
                            <Gauge className="h-5 w-5 text-purple-500" />
                            Altman Z-Score
                        </CardTitle>
                        <CardDescription className="text-gray-400">
                            Predicción de riesgo de quiebra
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {scoreData ? (
                            <div className="text-center py-6">
                                <div className={`text-5xl font-bold mb-2 ${getAltmanColor(scoreData.altmanZScore)}`}>
                                    {scoreData.altmanZScore.toFixed(2)}
                                </div>
                                <div className="text-sm text-gray-400 mb-4">
                                    {scoreData.altmanZScore > 3 ? "Zona Segura (Bajo Riesgo)" :
                                        scoreData.altmanZScore > 1.8 ? "Zona Gris (Riesgo Moderado)" : "Zona de Peligro (Alto Riesgo)"}
                                </div>
                                <Progress value={Math.min(scoreData.altmanZScore * 10, 100)} className="h-2 w-full bg-gray-800" />
                            </div>
                        ) : (
                            <p className="text-gray-500 text-center py-10">No disponible</p>
                        )}
                    </CardContent>
                </Card>

                {/* Piotroski Score */}
                <Card className="bg-gray-900 border-gray-800">
                    <CardHeader>
                        <CardTitle className="text-gray-100 flex items-center gap-2">
                            <Gauge className="h-5 w-5 text-blue-500" />
                            Piotroski F-Score
                        </CardTitle>
                        <CardDescription className="text-gray-400">
                            Fortaleza financiera (0-9)
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {scoreData ? (
                            <div className="text-center py-6">
                                <div className={`text-5xl font-bold mb-2 ${getPiotroskiColor(scoreData.piotroskiScore)}`}>
                                    {scoreData.piotroskiScore}/9
                                </div>
                                <div className="text-sm text-gray-400 mb-4">
                                    {scoreData.piotroskiScore >= 7 ? "Muy Fuerte" :
                                        scoreData.piotroskiScore >= 4 ? "Estable" : "Débil"}
                                </div>
                                <Progress value={(scoreData.piotroskiScore / 9) * 100} className="h-2 w-full bg-gray-800" />
                            </div>
                        ) : (
                            <p className="text-gray-500 text-center py-10">No disponible</p>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Peers */}
            <Card className="bg-gray-900 border-gray-800">
                <CardHeader>
                    <CardTitle className="text-gray-100 flex items-center gap-2">
                        <Users className="h-5 w-5 text-orange-500" />
                        Competidores y Pares
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-wrap gap-3">
                        {peerList.length > 0 ? (
                            peerList.map((peer, i) => (
                                <Link key={i} href={`/stocks/${peer}`}>
                                    <Badge variant="outline" className="text-base py-2 px-4 border-gray-700 hover:bg-gray-800 hover:text-white transition-colors cursor-pointer flex items-center gap-2">
                                        {peer}
                                        <ArrowUpRight className="h-3 w-3 text-gray-500" />
                                    </Badge>
                                </Link>
                            ))
                        ) : (
                            <p className="text-gray-500">No se encontraron competidores.</p>
                        )}
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}

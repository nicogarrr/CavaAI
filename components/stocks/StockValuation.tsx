'use client';

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FinancialScore, PeerCompany, getFinancialScores, getStockPeers } from "@/lib/actions/fmp.actions";
import { Gauge, Users, ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useStockCache } from "@/lib/cache/useSessionCache";

interface StockValuationProps {
    symbol: string;
}

interface CachedValuationData {
    scoreData: FinancialScore | null;
    peers: PeerCompany[];
}

export default function StockValuation({ symbol }: StockValuationProps) {
    // Use session cache to persist data between tab changes (15 min TTL)
    const {
        data: cachedData,
        setData: setCachedData
    } = useStockCache<CachedValuationData>(symbol, 'valuation', { ttlMinutes: 15 });

    const [scoreData, setScoreData] = useState<FinancialScore | null>(cachedData?.scoreData ?? null);
    const [peers, setPeers] = useState<PeerCompany[]>(cachedData?.peers ?? []);
    const [loading, setLoading] = useState(!cachedData);

    useEffect(() => {
        // If we have cached data, use it and skip fetch
        if (cachedData) {
            setScoreData(cachedData.scoreData);
            setPeers(cachedData.peers);
            setLoading(false);
            return;
        }

        const fetchData = async () => {
            setLoading(true);
            try {
                const [scores, peerData] = await Promise.all([
                    getFinancialScores(symbol),
                    getStockPeers(symbol)
                ]);
                setScoreData(scores);
                setPeers(peerData || []);
                // Save to cache
                setCachedData({ scoreData: scores, peers: peerData || [] });
            } catch (error) {
                console.error("Failed to fetch valuation data", error);
            } finally {
                setLoading(false);
            }
        };

        if (symbol) {
            fetchData();
        }
    }, [symbol, cachedData, setCachedData]);

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

    const formatMarketCap = (mktCap: number) => {
        if (mktCap >= 1e12) return `$${(mktCap / 1e12).toFixed(1)}T`;
        if (mktCap >= 1e9) return `$${(mktCap / 1e9).toFixed(1)}B`;
        if (mktCap >= 1e6) return `$${(mktCap / 1e6).toFixed(0)}M`;
        return `$${mktCap.toLocaleString()}`;
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
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                        {peers.length > 0 ? (
                            peers.slice(0, 12).map((peer, i) => (
                                <Link key={i} href={`/stocks/${peer.symbol}`}>
                                    <div className="p-3 rounded-lg border border-gray-700 hover:bg-gray-800 hover:border-gray-600 transition-colors cursor-pointer">
                                        <div className="flex items-center justify-between mb-1">
                                            <span className="font-semibold text-gray-100">{peer.symbol}</span>
                                            <ArrowUpRight className="h-3 w-3 text-gray-500" />
                                        </div>
                                        <div className="text-xs text-gray-400 truncate mb-1">{peer.companyName}</div>
                                        <div className="flex justify-between text-xs">
                                            <span className="text-gray-500">${peer.price?.toFixed(2) || 'N/A'}</span>
                                            <span className="text-gray-500">{formatMarketCap(peer.mktCap)}</span>
                                        </div>
                                    </div>
                                </Link>
                            ))
                        ) : (
                            <p className="text-gray-500 col-span-full">No se encontraron competidores.</p>
                        )}
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}

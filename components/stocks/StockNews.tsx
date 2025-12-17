'use client';

import { useEffect, useState } from 'react';
import { getCompanyNews } from '@/lib/actions/finnhub.actions';
import { getPressReleases, PressRelease } from '@/lib/actions/fmp.actions';
import PaginatedNews from './PaginatedNews';
import { Skeleton } from '@/components/ui/skeleton';
import { Loader2, Newspaper, FileText, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';

interface StockNewsProps {
    symbol: string;
}

type NewsTab = 'market' | 'press';

export default function StockNews({ symbol }: StockNewsProps) {
    const [activeTab, setActiveTab] = useState<NewsTab>('market');
    const [marketNews, setMarketNews] = useState<any[]>([]);
    const [pressReleases, setPressReleases] = useState<PressRelease[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchData() {
            try {
                setLoading(true);
                const [newsData, pressData] = await Promise.all([
                    getCompanyNews(symbol, 15),
                    getPressReleases(symbol, 10)
                ]);
                setMarketNews(newsData || []);
                setPressReleases(pressData?.pressReleases || []);
            } catch (err) {
                console.error('Error fetching news:', err);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, [symbol]);

    const formatDate = (dateStr: string) => {
        return new Date(dateStr).toLocaleDateString('es-ES', {
            day: '2-digit',
            month: 'short',
            year: 'numeric'
        });
    };

    if (loading) {
        return (
            <div className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
                <div className="flex items-center gap-2 mb-4">
                    <h2 className="text-lg font-semibold text-gray-200">Noticias</h2>
                    <Loader2 className="h-4 w-4 text-gray-400 animate-spin" />
                </div>
                <div className="space-y-3">
                    <Skeleton className="h-16 w-full bg-gray-700" />
                    <Skeleton className="h-16 w-full bg-gray-700" />
                    <Skeleton className="h-16 w-full bg-gray-700" />
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Tab Switcher */}
            <div className="flex gap-2 border-b border-gray-700 pb-2">
                <button
                    onClick={() => setActiveTab('market')}
                    className={cn(
                        "flex items-center gap-2 px-4 py-2 rounded-t-lg transition-colors",
                        activeTab === 'market'
                            ? "bg-blue-600/20 text-blue-400 border-b-2 border-blue-500"
                            : "text-gray-400 hover:text-gray-200"
                    )}
                >
                    <Newspaper className="h-4 w-4" />
                    Noticias de Mercado ({marketNews.length})
                </button>
                <button
                    onClick={() => setActiveTab('press')}
                    className={cn(
                        "flex items-center gap-2 px-4 py-2 rounded-t-lg transition-colors",
                        activeTab === 'press'
                            ? "bg-purple-600/20 text-purple-400 border-b-2 border-purple-500"
                            : "text-gray-400 hover:text-gray-200"
                    )}
                >
                    <FileText className="h-4 w-4" />
                    Comunicados Oficiales ({pressReleases.length})
                </button>
            </div>

            {/* Market News Tab */}
            {activeTab === 'market' && (
                <PaginatedNews articles={marketNews} itemsPerPage={5} />
            )}

            {/* Press Releases Tab */}
            {activeTab === 'press' && (
                <div className="space-y-3">
                    {pressReleases.length === 0 ? (
                        <p className="text-sm text-gray-500 text-center py-8">
                            No hay comunicados oficiales disponibles
                        </p>
                    ) : (
                        pressReleases.map((release, idx) => (
                            <div
                                key={idx}
                                className="p-4 rounded-lg border border-gray-700 bg-gray-800/50 hover:bg-gray-800/80 transition-colors"
                            >
                                <div className="flex items-start justify-between gap-3">
                                    <div className="flex-1 min-w-0">
                                        <h3 className="text-sm font-medium text-gray-100 line-clamp-2 mb-1">
                                            {release.title}
                                        </h3>
                                        <p className="text-xs text-gray-400 line-clamp-2">
                                            {release.text?.slice(0, 150)}...
                                        </p>
                                        <span className="text-xs text-gray-500 mt-2 inline-block">
                                            {formatDate(release.date)}
                                        </span>
                                    </div>
                                    <span className="shrink-0 px-2 py-1 text-xs bg-purple-900/50 text-purple-300 rounded">
                                        Oficial
                                    </span>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            )}
        </div>
    );
}


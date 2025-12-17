'use client';

import { useEffect, useState } from 'react';
import { getCompanyNews } from '@/lib/actions/finnhub.actions';
import PaginatedNews from './PaginatedNews';
import { Skeleton } from '@/components/ui/skeleton';
import { Loader2 } from 'lucide-react';

interface StockNewsProps {
    symbol: string;
}

export default function StockNews({ symbol }: StockNewsProps) {
    const [news, setNews] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchData() {
            try {
                setLoading(true);
                const articles = await getCompanyNews(symbol, 20);
                setNews(articles || []);
            } catch (err) {
                console.error('Error fetching news:', err);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, [symbol]);

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

    return <PaginatedNews articles={news} itemsPerPage={5} />;
}

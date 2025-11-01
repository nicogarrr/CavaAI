import { getPortfolioNews } from '@/lib/actions/portfolioNews.actions';
import Image from 'next/image';
import { Card } from '@/components/ui/card';
import { ExternalLink, Clock } from 'lucide-react';
import Link from 'next/link';
import PaginatedNews from '@/components/stocks/PaginatedNews';

interface PortfolioNewsProps {
    portfolioId: string;
}

export default async function PortfolioNews({ portfolioId }: PortfolioNewsProps) {
    const news = await getPortfolioNews(portfolioId, 20);

    if (news.length === 0) {
        return (
            <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
                <h2 className="text-xl font-semibold mb-4 text-gray-200">Noticias de la Cartera</h2>
                <div className="flex items-center justify-center h-48 text-gray-500">
                    <p>No hay noticias disponibles para los activos de esta cartera.</p>
                </div>
            </Card>
        );
    }

    // Convertir al formato esperado por PaginatedNews
    const articles = news.map(({ article, symbol, company }) => ({
        id: `${article.id || Math.random()}-${symbol}`,
        headline: article.headline || '',
        summary: article.summary || '',
        url: article.url || '',
        source: article.source || '',
        datetime: article.datetime || Date.now() / 1000,
        image: article.image,
        related: `${symbol} (${company})`,
    }));

    return (
        <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-gray-200">Noticias de la Cartera</h2>
                <span className="text-sm text-gray-400">{news.length} artículos</span>
            </div>
            
            <PaginatedNews articles={articles} itemsPerPage={5} />
        </Card>
    );
}


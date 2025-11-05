import { getCompanyNews } from '@/lib/actions/finnhub.actions';
import PaginatedNews from './PaginatedNews';

interface StockNewsProps {
    symbol: string;
}

export default async function StockNews({ symbol }: StockNewsProps) {
    const news = await getCompanyNews(symbol, 20);

    // Convertir MarketNewsArticle[] a NewsArticle[] (id: number -> id: string)
    const convertedNews = news.map((article) => ({
        id: String(article.id),
        headline: article.headline,
        summary: article.summary,
        url: article.url,
        source: article.source,
        datetime: article.datetime,
        image: article.image,
        related: article.related,
    }));

    return <PaginatedNews articles={convertedNews} itemsPerPage={5} />;
}


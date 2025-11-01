import { getCompanyNews } from '@/lib/actions/finnhub.actions';
import PaginatedNews from './PaginatedNews';

interface StockNewsProps {
    symbol: string;
}

export default async function StockNews({ symbol }: StockNewsProps) {
    const news = await getCompanyNews(symbol, 20);

    return <PaginatedNews articles={news} itemsPerPage={5} />;
}


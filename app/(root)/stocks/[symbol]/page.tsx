import { permanentRedirect } from 'next/navigation';

export default async function LegacyStockRedirect({ params }: StockDetailsPageProps) {
    const { symbol } = await params;
    permanentRedirect(`/research/${encodeURIComponent(symbol.toUpperCase())}`);
}

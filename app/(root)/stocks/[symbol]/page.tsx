import WatchlistButton from "@/components/WatchlistButton";
import StockPageLayout from "@/components/stocks/StockPageLayout";
import StockHeaderPrice from "@/components/stocks/StockHeaderPrice";
import { getProfile, getStockQuote } from "@/lib/actions/finnhub.actions";

export default async function StockDetails({ params }: StockDetailsPageProps) {
    const { symbol } = await params;

    // Parallelize initial critical data fetching (Header & Basic Info)
    const profilePromise = getProfile(symbol);
    const quotePromise = getStockQuote(symbol);

    // Obtener estado de watchlist
    const { getWatchlist } = await import("@/lib/actions/watchlist.actions");
    const watchlistPromise = getWatchlist();

    const [profile, quote, watchlist] = await Promise.all([
        profilePromise,
        quotePromise,
        watchlistPromise
    ]);

    const isInWatchlist = watchlist.some((item) => item.symbol === symbol.toUpperCase());
    const companyName = profile?.name || symbol;
    const currentPrice = quote?.c || 0;
    const priceChange = quote?.d || 0;
    const priceChangePercent = quote?.dp || 0;
    const upperSymbol = symbol.toUpperCase();

    return (
        <div className="flex flex-col min-h-screen">
            {/* Header Section - Always visible */}
            <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 px-6 pt-4 border-b border-gray-700/50 bg-gray-900/50 backdrop-blur-sm sticky top-0 z-10">
                <div className="flex items-center gap-4">
                    {/* Company Logo/Icon */}
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-bold text-lg shrink-0">
                        {upperSymbol.slice(0, 2)}
                    </div>
                    <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                            <h1 className="text-2xl font-bold text-gray-100">{companyName}</h1>
                            <span className="px-2 py-0.5 text-xs font-medium bg-gray-700/50 text-gray-300 rounded">
                                {upperSymbol}
                            </span>
                        </div>
                        {profile?.exchange && (
                            <p className="text-sm text-gray-400">{profile.exchange}</p>
                        )}
                    </div>
                </div>

                <div className="flex items-center gap-6">
                    {/* Price Display */}
                    <StockHeaderPrice
                        symbol={symbol}
                        initialPrice={currentPrice}
                        initialChange={priceChange}
                        initialChangePercent={priceChangePercent}
                    />
                    <WatchlistButton
                        symbol={upperSymbol}
                        company={companyName}
                        isInWatchlist={isInWatchlist}
                    />
                </div>
            </header>

            {/* Main Content with Sidebar */}
            <StockPageLayout
                symbol={upperSymbol}
                companyName={companyName}
                currentPrice={currentPrice}
            />
        </div>
    );
}

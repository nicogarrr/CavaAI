import { notFound } from 'next/navigation';
import { getProfile, getETFHoldings, getCandles } from '@/lib/actions/finnhub.actions';
import FundHeader from '@/components/funds/FundHeader';
import FundProfile from '@/components/funds/FundProfile';
import FundPerformance from '@/components/funds/FundPerformance';
import FundHoldings from '@/components/funds/FundHoldings';
import FundRiskMetrics from '@/components/funds/FundRiskMetrics';
import FundComparison from '@/components/funds/FundComparison';

type FundDetailPageProps = {
  params: Promise<{ symbol: string }>;
};

export default async function FundDetailPage({ params }: FundDetailPageProps) {
  const { symbol } = await params;
  const upperSymbol = symbol.toUpperCase();

  try {
    // Fetch all data in parallel
    const [profile, holdings, candles] = await Promise.all([
      getProfile(upperSymbol),
      getETFHoldings(upperSymbol),
      getCandles(upperSymbol, Math.floor((Date.now() - 365 * 24 * 60 * 60 * 1000) / 1000), Math.floor(Date.now() / 1000), 'D', 3600)
    ]);

    if (!profile) {
      notFound();
    }

    const fundData = {
      symbol: upperSymbol,
      profile,
      holdings: holdings.holdings || [],
      candles: candles.s === 'ok' ? candles : null,
    };

    return (
      <div className="flex min-h-screen flex-col p-6">
        <FundHeader fundData={fundData} />
        
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
          <div className="lg:col-span-2 space-y-6">
            <FundProfile fundData={fundData} />
            <FundPerformance fundData={fundData} />
            <FundHoldings fundData={fundData} />
          </div>
          
          <div className="space-y-6">
            <FundRiskMetrics fundData={fundData} />
            <FundComparison fundData={fundData} />
          </div>
        </div>
      </div>
    );
  } catch (error) {
    console.error('Error loading fund data:', error);
    notFound();
  }
}

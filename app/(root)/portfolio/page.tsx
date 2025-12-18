import { Suspense } from 'react';
import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { getPortfolioSummary, getPortfolioTransactions, getPortfolioScores } from '@/lib/actions/portfolio.actions';
import PortfolioSummary from '@/components/portfolio/PortfolioSummary';
import PortfolioHoldings from '@/components/portfolio/PortfolioHoldings';
import PortfolioTransactions from '@/components/portfolio/PortfolioTransactions';
import PortfolioScores from '@/components/portfolio/PortfolioScores';
import AddTransactionButton from '@/components/portfolio/AddTransactionButton';
import ImportFromImage from '@/components/portfolio/ImportFromImage';
import RefreshPortfolioButton from '@/components/portfolio/RefreshPortfolioButton';
import { PortfolioStrategyInsight } from '@/components/portfolio/PortfolioStrategyInsight';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Wallet } from 'lucide-react';

// Forzar renderizado dinámico
export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function PortfolioPage() {
  // Permitir acceso en desarrollo sin autenticación
  let userId = 'dev-user-123';

  try {
    const auth = await getAuth();
    if (auth) {
      const session = await auth.api.getSession({ headers: await headers() });
      if (session?.user?.id) {
        userId = session.user.id;
      } else if (process.env.NODE_ENV !== 'development') {
        redirect('/sign-in');
      }
    }
  } catch (error) {
    if (process.env.NODE_ENV !== 'development') {
      redirect('/sign-in');
    }
  }

  const [summary, transactions, scores] = await Promise.all([
    getPortfolioSummary(userId),
    getPortfolioTransactions(userId),
    getPortfolioScores(userId),
  ]);

  return (
    <div className="flex min-h-screen flex-col p-6">
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Wallet className="h-8 w-8 text-teal-400" />
            <div>
              <h1 className="text-3xl font-bold text-gray-100">Mi Cartera</h1>
              <p className="text-gray-400 mt-1">
                Seguimiento de tus inversiones personales
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <RefreshPortfolioButton userId={userId} />
            <ImportFromImage userId={userId} />
            <AddTransactionButton userId={userId} />
          </div>
        </div>
      </div>

      {/* Summary */}
      <div className="mb-6">
        <PortfolioSummary summary={summary} />
      </div>

      {/* Scores */}
      <div className="mb-6">
        <PortfolioScores scores={scores} />
      </div>

      {/* Strategy Analysis */}
      <div className="mb-6">
        <PortfolioStrategyInsight portfolioSummary={summary} />
      </div>

      {/* Holdings and Transactions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <PortfolioHoldings holdings={summary.holdings} userId={userId} />
        </div>
        <div>
          <PortfolioTransactions transactions={transactions} userId={userId} />
        </div>
      </div>
    </div>
  );
}


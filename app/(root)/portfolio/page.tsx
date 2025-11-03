import { Suspense } from 'react';
import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { getPortfolioSummary, getPortfolioTransactions } from '@/lib/actions/portfolio.actions';
import PortfolioSummary from '@/components/portfolio/PortfolioSummary';
import PortfolioHoldings from '@/components/portfolio/PortfolioHoldings';
import PortfolioTransactions from '@/components/portfolio/PortfolioTransactions';
import AddTransactionButton from '@/components/portfolio/AddTransactionButton';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Wallet } from 'lucide-react';

// Forzar renderizado dinámico
export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function PortfolioPage() {
  const auth = await getAuth();
  if (!auth) redirect('/sign-in');
  
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user) redirect('/sign-in');
  
  const userId = session.user.id;
  
  const [summary, transactions] = await Promise.all([
    getPortfolioSummary(userId),
    getPortfolioTransactions(userId),
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
          <AddTransactionButton userId={userId} />
        </div>
      </div>

      {/* Summary */}
      <div className="mb-6">
        <PortfolioSummary summary={summary} />
      </div>

      {/* Holdings and Transactions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <PortfolioHoldings holdings={summary.holdings} />
        </div>
        <div>
          <PortfolioTransactions transactions={transactions} userId={userId} />
        </div>
      </div>
    </div>
  );
}

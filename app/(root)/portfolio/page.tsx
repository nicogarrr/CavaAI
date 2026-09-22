import { redirect } from 'next/navigation';
import { getPortfolioSummary, getPortfolioTransactions, getPortfolioScores, getPortfolioTearsheet } from '@/lib/actions/portfolio.actions';
import PortfolioTabs from '@/components/portfolio/PortfolioTabs';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import BackendOffline from '@/components/system/BackendOffline';
import { isBackendUnavailableError } from '@/lib/backend-offline';

// Forzar renderizado dinámico
export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function PortfolioPage() {
  let userId: string;

  try {
    userId = (await requireAuthenticatedUser()).id;
  } catch {
    redirect('/sign-in');
  }

  const fetchAll = () =>
    Promise.all([
      getPortfolioSummary(userId),
      getPortfolioTransactions(userId),
      getPortfolioScores(userId),
      getPortfolioTearsheet(userId),
    ]);

  let result: Awaited<ReturnType<typeof fetchAll>>;
  try {
    result = await fetchAll();
  } catch (error) {
    if (isBackendUnavailableError(error)) {
      return <BackendOffline feature="Tu cartera" retryHref="/portfolio" />;
    }
    throw error;
  }
  const [summary, transactions, scores, tearsheet] = result;

  return (
    <PortfolioTabs
      summary={summary}
      transactions={transactions}
      scores={scores}
      tearsheet={tearsheet}
      userId={userId}
    />
  );
}

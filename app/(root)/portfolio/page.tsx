import { redirect } from 'next/navigation';
import { getPortfolioSummary, getPortfolioTransactions, getPortfolioScores, getPortfolioTearsheet } from '@/lib/actions/portfolio.actions';
import PortfolioTabs from '@/components/portfolio/PortfolioTabs';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';

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

  const [summary, transactions, scores, tearsheet] = await Promise.all([
    getPortfolioSummary(userId),
    getPortfolioTransactions(userId),
    getPortfolioScores(userId),
    getPortfolioTearsheet(userId),
  ]);

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

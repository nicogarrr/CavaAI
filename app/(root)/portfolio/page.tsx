import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { getPortfolioSummary, getPortfolioTransactions, getPortfolioScores } from '@/lib/actions/portfolio.actions';
import PortfolioTabs from '@/components/portfolio/PortfolioTabs';

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
    <PortfolioTabs
      summary={summary}
      transactions={transactions}
      userId={userId}
    />
  );
}

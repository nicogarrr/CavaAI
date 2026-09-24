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

  let result: [
    Awaited<ReturnType<typeof getPortfolioSummary>>,
    Awaited<ReturnType<typeof getPortfolioTransactions>>,
    Awaited<ReturnType<typeof getPortfolioScores>>,
    Awaited<ReturnType<typeof getPortfolioTearsheet>>,
  ];
  let partialMessage: string | null = null;
  try {
    // Cada lectura va con su propio catch para que un módulo lento no
    // oculte el resto de la cartera. Summary/positions son esenciales; scores,
    // transactions y tearsheet son lecturas tolerantes a falta de historial.
    const [summaryResult, transactionsResult, scoresResult, tearsheetResult] = await Promise.all([
      getPortfolioSummary(userId).then((value) => ({ value, error: null as string | null })).catch((error) => ({ value: null, error: error instanceof Error ? error.message : 'No se pudo cargar la cartera' })),
      getPortfolioTransactions(userId).then((value) => ({ value, error: null as string | null })).catch((error) => ({ value: [] as Awaited<ReturnType<typeof getPortfolioTransactions>>, error: error instanceof Error ? error.message : 'No se pudieron cargar los movimientos' })),
      getPortfolioScores(userId).then((value) => ({ value, error: null as string | null })).catch((error) => ({ value: { quality: 0, growth: 0, value: 0, dividend: 0, cagr3y: 0 }, error: error instanceof Error ? error.message : 'No se pudieron cargar los factores' })),
      getPortfolioTearsheet(userId).then((value) => ({ value, error: null as string | null })).catch((error) => ({ value: null, error: error instanceof Error ? error.message : 'No se pudo cargar el historial' })),
    ]);
    if (!summaryResult.value) {
      const error = new Error(summaryResult.error ?? 'No se pudo cargar la cartera');
      if (isBackendUnavailableError(error)) return <BackendOffline feature="Tu cartera" retryHref="/portfolio" />;
      throw error;
    }
    result = [summaryResult.value, transactionsResult.value, scoresResult.value, tearsheetResult.value];
    const secondaryErrors = [transactionsResult.error, scoresResult.error, tearsheetResult.error]
      .filter((error): error is string => Boolean(error));
    partialMessage = secondaryErrors.length ? `Algunas secciones no respondieron: ${secondaryErrors.join(' · ')}` : null;
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
      partialMessage={partialMessage}
    />
  );
}

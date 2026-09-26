import { FileText } from 'lucide-react';
import { getResearchDashboard } from '@/lib/actions/research.actions';
import BackendOffline from '@/components/system/BackendOffline';
import { isBackendUnavailableError } from '@/lib/backend-offline';
import WorkProductButton from '@/components/work-products/WorkProductButton';
import { formatMoney, formatPercent } from '@/lib/format';
import { PageHeader } from '@/components/ui/page-header';
import { Stat } from '@/components/ui/stat';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

function money(value: number) {
  return formatMoney(value, 'USD', { maximumFractionDigits: 0 });
}

function pct(value: number) {
  return formatPercent(value, { fromRatio: true, digits: 1 });
}

export default async function ResearchPage() {
  let dashboard: Awaited<ReturnType<typeof getResearchDashboard>>;
  try {
    dashboard = await getResearchDashboard();
  } catch (error) {
    if (isBackendUnavailableError(error)) {
      return <BackendOffline feature="Research" retryHref="/research" />;
    }
    throw error;
  }
  const { portfolio } = dashboard;

  return (
    <main id="content" tabIndex={-1} className="mx-auto flex max-w-7xl flex-col gap-6">
      <PageHeader
        actions={<WorkProductButton />}
        description="Tesis versionadas, auditoría de fuentes, valoración determinista, riesgo y workflows conectados al backend Python."
        kicker="Research OS"
        title="Mesa de research de cartera"
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Stat label="Valor total" value={money(portfolio.total_value)} />
        <Stat label="Equity" value={money(portfolio.equity_value)} />
        <Stat label="Top 1" value={pct(portfolio.top_1_weight)} tone="warn" />
        <Stat label="Alertas" value={String(portfolio.alerts.length)} tone={portfolio.alerts.length ? 'bad' : 'good'} />
      </section>

      <section className="rounded-lg border border-gray-800 bg-surface-1 p-5">
        <div className="mb-4 flex items-center gap-2">
          <FileText className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Alertas de cartera</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {portfolio.alerts.length ? (
            portfolio.alerts.map((alert, index) => (
              <div key={`${alert.message}-${index}`} className="rounded-md border border-red-900/50 bg-red-950/20 p-3 text-sm">
                <div className="font-semibold text-red-200">{alert.message}</div>
                <div className="mt-1 text-red-300/70">{pct(alert.metric_value)} vs {pct(alert.threshold)}</div>
              </div>
            ))
          ) : (
            <div className="rounded-md border border-gray-800 p-3 text-sm text-gray-400">Sin alertas activas.</div>
          )}
        </div>
      </section>
    </main>
  );
}

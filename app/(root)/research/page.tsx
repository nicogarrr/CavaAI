import { FileText } from 'lucide-react';
import { getResearchDashboard } from '@/lib/actions/research.actions';
import BackendOffline from '@/components/system/BackendOffline';
import { isBackendUnavailableError } from '@/lib/backend-offline';
import WorkProductButton from '@/components/work-products/WorkProductButton';
import { formatMoney, formatPercent } from '@/lib/format';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

function money(value: number) {
  return formatMoney(value, 'USD', { maximumFractionDigits: 0 });
}

function pct(value: number) {
  return formatPercent(value, { fromRatio: true, digits: 1 });
}

function Stat({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: string;
  tone?: 'default' | 'good' | 'warn' | 'bad';
}) {
  const toneClass = {
    default: 'text-gray-100',
    good: 'text-teal-300',
    warn: 'text-amber-300',
    bad: 'text-red-300',
  }[tone];

  return (
    <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
      <div className="text-xs font-semibold uppercase text-gray-500">{label}</div>
      <div className={`mt-2 text-2xl font-semibold ${toneClass}`}>{value}</div>
    </div>
  );
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
    <main className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="flex flex-col gap-3 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase text-teal-300">Research OS</p>
          <h1 className="mt-1 text-3xl font-bold text-gray-100">Mesa de research de cartera</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Tesis versionadas, auditoría de fuentes, valoración determinista, riesgo y workflows conectados al backend Python.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <WorkProductButton />
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Stat label="Valor total" value={money(portfolio.total_value)} />
        <Stat label="Equity" value={money(portfolio.equity_value)} />
        <Stat label="Top 1" value={pct(portfolio.top_1_weight)} tone="warn" />
        <Stat label="Alertas" value={String(portfolio.alerts.length)} tone={portfolio.alerts.length ? 'bad' : 'good'} />
      </section>

      <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
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

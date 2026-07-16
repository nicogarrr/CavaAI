import { ArrowLeft, CheckCircle2, Cpu, Database, DollarSign, XCircle } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { getResearchDashboard } from '@/lib/actions/research.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const CONNECTOR_META: Record<string, { label: string; description: string }> = {
  fmp: { label: 'FMP', description: 'Financial Modeling Prep — earnings, balance sheet, ratios' },
  ibkr: { label: 'IBKR', description: 'Interactive Brokers Flex XML — live portfolio positions' },
  fred: { label: 'FRED', description: 'Federal Reserve FRED — macro rates, CPI, GDP' },
  manual_transcript_import: { label: 'Manual transcripts', description: 'Provider-neutral transcript text import' },
  langfuse: { label: 'Langfuse', description: 'Langfuse — LLM observability and tracing' },
  qdrant_url: { label: 'Qdrant', description: 'Qdrant — vector store for RAG search' },
};

const CONNECTOR_ORDER = ['fmp', 'ibkr', 'fred', 'manual_transcript_import', 'langfuse', 'qdrant_url'];

function connectorStatus(value: boolean | string): 'configured' | 'not_configured' | 'manual' {
  if (value === true || (typeof value === 'string' && value.length > 0 && value !== 'false')) return 'configured';
  if (value === 'manual') return 'manual';
  return 'not_configured';
}

export default async function ResearchSettingsPage() {
  const { settings } = await getResearchDashboard();

  const orderedConnectors = CONNECTOR_ORDER.map((key) => ({
    key,
    value: settings.connectors[key] ?? false,
  }));

  const extraConnectors = Object.entries(settings.connectors).filter(
    ([key]) => !CONNECTOR_ORDER.includes(key),
  );

  const allConnectors = [
    ...orderedConnectors,
    ...extraConnectors.map(([key, value]) => ({ key, value })),
  ];

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="flex flex-col gap-4 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <Button asChild className="mb-4" size="sm" variant="ghost">
            <Link href="/research">
              <ArrowLeft className="h-4 w-4" />
              Research
            </Link>
          </Button>
          <p className="text-sm font-semibold uppercase text-teal-300">Configuration</p>
          <h1 className="mt-1 text-3xl font-bold text-gray-100">Settings & Connectors</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Estado de conectores externos, presupuesto LLM y runtime del backend.
          </p>
        </div>
        <div className="rounded-lg border border-gray-800 bg-[#111111] px-4 py-3 text-sm text-gray-300">
          {settings.app_env}
        </div>
      </header>

      <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
        <div className="mb-4 flex items-center gap-2">
          <Database className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Connectors</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {allConnectors.map(({ key, value }) => {
            const meta = CONNECTOR_META[key];
            const status = connectorStatus(value);
            const statusBadge =
              status === 'configured'
                ? 'border-teal-800 bg-teal-950/30 text-teal-300'
                : status === 'manual'
                  ? 'border-amber-800 bg-amber-950/30 text-amber-300'
                  : 'border-gray-700 bg-gray-900 text-gray-500';

            return (
              <div key={key} className="rounded-md border border-gray-800 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    {status === 'configured' ? (
                      <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-teal-300" />
                    ) : (
                      <XCircle className="h-4 w-4 flex-shrink-0 text-gray-600" />
                    )}
                    <span className="font-semibold text-gray-200">{meta?.label ?? key}</span>
                  </div>
                  <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${statusBadge}`}>
                    {status.replace('_', ' ')}
                  </span>
                </div>
                <p className="mt-2 text-xs text-gray-500">{meta?.description ?? key}</p>
              </div>
            );
          })}
        </div>
      </section>

      <section className="grid gap-6 md:grid-cols-2">
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <DollarSign className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Budget</h2>
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between rounded-md border border-gray-800 p-3">
              <span className="text-gray-400">Daily cost / cap</span>
              <span className="font-semibold text-gray-200">
                {settings.budget.daily_cost_eur.toFixed(2)} / {settings.budget.daily_cap_eur.toFixed(2)} EUR
              </span>
            </div>
            <div className="flex items-center justify-between rounded-md border border-gray-800 p-3">
              <span className="text-gray-400">Monthly cost / cap</span>
              <span className="font-semibold text-gray-200">
                {settings.budget.monthly_cost_eur.toFixed(2)} / {settings.budget.monthly_cap_eur.toFixed(2)} EUR
              </span>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <Cpu className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Runtime</h2>
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between rounded-md border border-gray-800 p-3">
              <span className="text-gray-400">Environment</span>
              <span className="font-semibold text-gray-200">{settings.app_env}</span>
            </div>
            <div className="flex items-center justify-between rounded-md border border-gray-800 p-3">
              <span className="text-gray-400">MAF version</span>
              <span className="font-mono font-semibold text-gray-200">{settings.maf_version}</span>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

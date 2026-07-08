import {
  Activity,
  BriefcaseBusiness,
  Database,
  FileText,
  GitBranch,
  ShieldCheck,
} from 'lucide-react';
import Link from 'next/link';
import { getResearchDashboard } from '@/lib/actions/research.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

function money(value: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(Number.isFinite(value) ? value : 0);
}

function pct(value: number) {
  return `${((Number.isFinite(value) ? value : 0) * 100).toFixed(1)}%`;
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
  const { companies, portfolio, workflows, settings } = await getResearchDashboard();
  const configuredConnectors = Object.entries(settings.connectors).filter(([, value]) => Boolean(value));
  const topCompanies = companies.slice(0, 8);

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="flex flex-col gap-3 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase text-teal-300">Research OS</p>
          <h1 className="mt-1 text-3xl font-bold text-gray-100">Portfolio Research Desk</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Tesis versionadas, auditoria de fuentes, valoracion determinista, riesgo y workflows conectados al backend Python.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-gray-800 bg-[#111111] px-3 py-2 text-sm text-gray-300">
          <Activity className="h-4 w-4 text-teal-300" />
          {settings.app_env} - {settings.maf_version}
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Stat label="Valor total" value={money(portfolio.total_value)} />
        <Stat label="Equity" value={money(portfolio.equity_value)} />
        <Stat label="Top 1" value={pct(portfolio.top_1_weight)} tone="warn" />
        <Stat label="Alertas" value={String(portfolio.alerts.length)} tone={portfolio.alerts.length ? 'bad' : 'good'} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <BriefcaseBusiness className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Company Master</h2>
            <span className="ml-auto text-sm text-gray-500">{companies.length} empresas</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="text-xs uppercase text-gray-500">
                <tr>
                  <th className="border-b border-gray-800 py-2">Ticker</th>
                  <th className="border-b border-gray-800 py-2">Nombre</th>
                  <th className="border-b border-gray-800 py-2">Tipo</th>
                  <th className="border-b border-gray-800 py-2">Modelo</th>
                  <th className="border-b border-gray-800 py-2">Factores</th>
                </tr>
              </thead>
              <tbody>
                {topCompanies.map((company) => (
                  <tr key={company.ticker} className="border-b border-gray-900 last:border-0">
                    <td className="py-3 font-semibold text-gray-100">
                      <Link className="text-teal-300 hover:text-teal-200" href={`/research/${company.ticker}`}>
                        {company.ticker}
                      </Link>
                    </td>
                    <td className="py-3 text-gray-300">{company.name}</td>
                    <td className="py-3 text-gray-400">{company.company_type}</td>
                    <td className="py-3 text-gray-400">{company.valuation_model}</td>
                    <td className="py-3 text-gray-500">{company.factor_tags.slice(0, 4).join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Source Policy</h2>
          </div>
          <div className="grid gap-3 text-sm">
            {['No source -> no claim', 'No trace -> no valuation', 'No date -> no event', 'No diff -> no thesis update'].map((rule) => (
              <div key={rule} className="rounded-md border border-gray-800 bg-black/30 p-3 font-semibold text-gray-300">
                {rule}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <GitBranch className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Workflows</h2>
          </div>
          <div className="space-y-3">
            {workflows.slice(0, 5).map((workflow) => (
              <div key={workflow.name} className="rounded-md border border-gray-800 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold text-gray-100">{workflow.name}</span>
                  <span className="text-xs text-gray-500">{workflow.steps.length} steps</span>
                </div>
                <p className="mt-1 text-sm text-gray-500">Input: {workflow.input}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <Database className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Runtime</h2>
          </div>
          <div className="grid gap-3 text-sm">
            <div className="rounded-md border border-gray-800 p-3 text-gray-300">
              LLM mensual: {settings.budget.monthly_cost_eur.toFixed(2)} / {settings.budget.monthly_cap_eur.toFixed(2)} EUR
            </div>
            <div className="rounded-md border border-gray-800 p-3 text-gray-300">
              LLM diario: {settings.budget.daily_cost_eur.toFixed(2)} / {settings.budget.daily_cap_eur.toFixed(2)} EUR
            </div>
            <div className="rounded-md border border-gray-800 p-3 text-gray-300">
              Conectores activos: {configuredConnectors.length || 0}
            </div>
          </div>
        </div>
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

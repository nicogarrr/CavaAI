import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  ArrowLeft,
  BarChart3,
  Database,
  FileText,
  GitBranch,
  RefreshCcw,
  ShieldCheck,
  Sigma,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  getResearchCompanyDetail,
  generateResearchThesis,
  refreshCompanyFinancials,
  refreshCompanyFinancialsSEC,
  getThesisHistory,
  type ResearchFact,
  type ResearchThesis,
  type ResearchThesisVersion,
  type ResearchValuation,
} from '@/lib/actions/research.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type ResearchCompanyPageProps = {
  params: Promise<{
    ticker: string;
  }>;
};

function money(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'N/A';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value);
}

function compactMoney(value: number) {
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(Number.isFinite(value) ? value : 0);
}

function pct(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'N/A';
  return `${(value * 100).toFixed(1)}%`;
}

function numberValue(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function FactValue({ fact }: { fact: ResearchFact }) {
  const value = numberValue(fact.value);
  if (fact.unit === 'decimal') return <>{pct(value)}</>;
  if (fact.unit === 'shares') return <>{compactMoney(value)}</>;
  if (fact.unit.toLowerCase().includes('usd')) return <>{compactMoney(value)}</>;
  return <>{value.toLocaleString('en-US')}</>;
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

function ValuationTable({ valuation }: { valuation: ResearchValuation }) {
  if (valuation.status === 'insufficient_data') {
    const missing = valuation.missing_inputs?.length
      ? valuation.missing_inputs
      : ((valuation.trace.missing_inputs as string[] | undefined) ?? []);
    return (
      <div className="space-y-3 text-sm">
        <div className="rounded-md border border-amber-900/70 bg-amber-950/20 p-3 text-amber-100">
          <div className="font-semibold">NO VALUATION — insufficient data</div>
          <p className="mt-2 text-amber-200/90">
            CavaAI no publica fair value con bootstrap assumptions. Ingiere hechos coherentes antes de confiar en un precio objetivo.
          </p>
        </div>
        {missing.length ? (
          <ul className="list-disc space-y-1 pl-5 text-gray-300">
            {missing.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }

  const scenarios = [
    { name: 'Bear', value: valuation.bear_value },
    { name: 'Base', value: valuation.base_value },
    { name: 'Bull', value: valuation.bull_value },
  ];

  return (
    <div className="space-y-3">
      {valuation.publishable === false ? (
        <div className="rounded-md border border-amber-900/70 bg-amber-950/20 p-3 text-sm text-amber-200">
          Valores parciales — no tratar como fair value final ({valuation.status}).
        </div>
      ) : null}
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-500">
          <tr>
            <th className="border-b border-gray-800 py-2">Escenario</th>
            <th className="border-b border-gray-800 py-2 text-right">Valor por accion</th>
            <th className="border-b border-gray-800 py-2 text-right">Upside</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((scenario) => (
            <tr key={scenario.name} className="border-b border-gray-900 last:border-0">
              <td className="py-3 font-semibold text-gray-200">{scenario.name}</td>
              <td className="py-3 text-right text-gray-300">{money(scenario.value)}</td>
              <td className="py-3 text-right text-gray-400">
                {valuation.current_price && scenario.value != null
                  ? pct(scenario.value / valuation.current_price - 1)
                  : 'N/A'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SensitivityGrid({ valuation }: { valuation: ResearchValuation }) {
  const rows = valuation.sensitivity.rows ?? [];
  const waccValues = rows[0]?.values?.map((item) => item.wacc) ?? [];

  if (!rows.length || !waccValues.length) {
    return <div className="rounded-md border border-gray-800 p-3 text-sm text-gray-500">Sin sensibilidad disponible.</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-right text-sm">
        <thead className="text-xs uppercase text-gray-500">
          <tr>
            <th className="border-b border-gray-800 py-2 text-left">Growth / WACC</th>
            {waccValues.map((wacc) => (
              <th key={wacc} className="border-b border-gray-800 py-2">{pct(wacc)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.revenue_growth} className="border-b border-gray-900 last:border-0">
              <td className="py-3 text-left font-semibold text-gray-300">{pct(row.revenue_growth)}</td>
              {row.values.map((item) => (
                <td key={`${row.revenue_growth}-${item.wacc}`} className="py-3 text-gray-400">
                  {money(item.value_per_share)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FactsTable({ facts }: { facts: ResearchFact[] }) {
  const visibleFacts = facts.slice(0, 40);

  if (!visibleFacts.length) {
    return (
      <div className="rounded-md border border-gray-800 p-4 text-sm text-gray-400">
        No hay facts financieros normalizados todavia. Configura FMP_API_KEY y pulsa Refresh FMP.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] text-left text-sm">
        <thead className="text-xs uppercase text-gray-500">
          <tr>
            <th className="border-b border-gray-800 py-2">Metric</th>
            <th className="border-b border-gray-800 py-2 text-right">Value</th>
            <th className="border-b border-gray-800 py-2">Period</th>
            <th className="border-b border-gray-800 py-2">Source</th>
            <th className="border-b border-gray-800 py-2">Type</th>
            <th className="border-b border-gray-800 py-2 text-right">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {visibleFacts.map((fact) => (
            <tr key={fact.id} className="border-b border-gray-900 last:border-0">
              <td className="py-3 font-semibold text-gray-200">{fact.metric}</td>
              <td className="py-3 text-right text-gray-300"><FactValue fact={fact} /></td>
              <td className="py-3 text-gray-400">{fact.period}</td>
              <td className="py-3 text-gray-400">{fact.source_type}</td>
              <td className="py-3">
                <Badge className="border-gray-700 bg-gray-900 text-gray-300" variant="outline">
                  {fact.is_reported ? 'reported' : 'derived'}
                </Badge>
              </td>
              <td className="py-3 text-right text-gray-400">{pct(numberValue(fact.confidence))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ThesisPanel({ thesis }: { thesis: ResearchThesis | null }) {
  if (!thesis) {
    return (
      <div className="rounded-md border border-gray-800 p-4 text-sm text-gray-400">
        No hay tesis generada para este ticker.
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <div className="grid gap-3 md:grid-cols-4">
        <Stat label="Version" value={`v${thesis.version}`} />
        <Stat label="Status" value={thesis.status} tone={thesis.status === 'final' ? 'good' : 'warn'} />
        <Stat label="Rating" value={thesis.rating} tone={thesis.rating === 'blocked' ? 'bad' : 'default'} />
        <Stat label="Source score" value={`${thesis.source_coverage_score}`} tone={thesis.source_coverage_score > 80 ? 'good' : 'warn'} />
      </div>
      <div className="rounded-md border border-gray-800 bg-black/30 p-4">
        <div className="text-xs font-semibold uppercase text-gray-500">Executive summary</div>
        <p className="mt-2 text-sm leading-6 text-gray-300">{thesis.executive_summary}</p>
      </div>
      <article className="max-h-[680px] overflow-auto rounded-md border border-gray-800 bg-black/30 p-4">
        <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6 text-gray-300">
          {thesis.thesis_markdown}
        </pre>
      </article>
    </div>
  );
}

export default async function ResearchCompanyPage({ params }: ResearchCompanyPageProps) {
  const { ticker } = await params;
  const [{ company, valuation, facts, thesis }, thesisHistory] = await Promise.all([
    getResearchCompanyDetail(ticker),
    getThesisHistory(ticker),
  ]);

  if (!company) notFound();

  const inputSource = valuation.trace.input_source ?? valuation.status ?? 'unknown';
  const sourceTone =
    inputSource === 'financial_facts' ? 'good' : inputSource === 'insufficient_data' ? 'bad' : 'warn';
  const marginTone =
    valuation.margin_of_safety == null
      ? 'warn'
      : valuation.margin_of_safety > 0.25
        ? 'good'
        : valuation.margin_of_safety < -0.15
          ? 'bad'
          : 'warn';
  const engine = (valuation.trace.engine as string | undefined) ?? valuation.model_type;

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
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold text-gray-100">{company.ticker}</h1>
            <Badge className="border-teal-800 bg-teal-950/30 text-teal-200" variant="outline">
              {company.valuation_model}
            </Badge>
            <Badge className="border-gray-700 bg-gray-900 text-gray-300" variant="outline">
              {company.company_type}
            </Badge>
            <Badge
              className={
                valuation.publishable === false
                  ? 'border-amber-800 bg-amber-950/30 text-amber-200'
                  : 'border-teal-800 bg-teal-950/30 text-teal-200'
              }
              variant="outline"
            >
              {valuation.publishable === false ? 'not publishable' : engine}
            </Badge>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            {company.name} - {company.sector} / {company.industry}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {company.factor_tags.map((tag) => (
              <span key={tag} className="rounded-md border border-gray-800 bg-[#111111] px-2 py-1 text-xs text-gray-400">
                {tag}
              </span>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <form action={refreshCompanyFinancials.bind(null, company.ticker)}>
            <Button type="submit" variant="outline">
              <RefreshCcw className="h-4 w-4" />
              Refresh FMP
            </Button>
          </form>
          <form action={refreshCompanyFinancialsSEC.bind(null, company.ticker)}>
            <Button type="submit" variant="outline">
              <RefreshCcw className="h-4 w-4" />
              Refresh SEC
            </Button>
          </form>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Stat label="Precio actual" value={money(valuation.current_price)} />
        <Stat label="Expected value" value={money(valuation.expected_value)} />
        <Stat label="Margin of safety" value={pct(valuation.margin_of_safety)} tone={marginTone} />
        <Stat label="Input source" value={inputSource.replaceAll('_', ' ')} tone={sourceTone} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Valuation</h2>
          </div>
          <ValuationTable valuation={valuation} />
        </div>

        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <Sigma className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Sensitivity</h2>
          </div>
          <SensitivityGrid valuation={valuation} />
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <Database className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Financial Facts</h2>
            <span className="ml-auto text-sm text-gray-500">{facts.length} facts</span>
          </div>
          <FactsTable facts={facts} />
        </div>

        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Audit Trace</h2>
          </div>
          <div className="space-y-3 text-sm">
            <div className="rounded-md border border-gray-800 p-3">
              <div className="text-xs font-semibold uppercase text-gray-500">Metodo</div>
              <div className="mt-1 text-gray-200">{valuation.trace.method ?? valuation.model_type}</div>
            </div>
            <div className="rounded-md border border-gray-800 p-3">
              <div className="text-xs font-semibold uppercase text-gray-500">Reverse DCF growth</div>
              <div className="mt-1 text-gray-200">{pct(valuation.reverse_dcf.required_revenue_growth ?? 0)}</div>
            </div>
            <div className="rounded-md border border-gray-800 p-3">
              <div className="text-xs font-semibold uppercase text-gray-500">Fact IDs</div>
              <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs text-gray-400">
                {JSON.stringify(valuation.trace.fact_ids ?? {}, null, 2)}
              </pre>
            </div>
            {valuation.trace.notice || valuation.status === 'insufficient_data' ? (
              <div className="rounded-md border border-amber-900/70 bg-amber-950/20 p-3 text-amber-200">
                {(valuation.trace.notice as string | undefined) ??
                  'Valuation blocked: bootstrap assumptions are disabled. Ingest coherent financial facts.'}
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Thesis</h2>
          </div>
          <form action={generateResearchThesis.bind(null, company.ticker)}>
            <Button type="submit" variant="outline">
              <FileText className="h-4 w-4" />
              Generate Thesis
            </Button>
          </form>
        </div>
        <ThesisPanel thesis={thesis} />
      </section>

      {thesisHistory.length > 0 && (
        <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <GitBranch className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Thesis History</h2>
            <span className="ml-auto text-sm text-gray-500">{thesisHistory.length} versions</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-gray-500">
                <tr>
                  <th className="border-b border-gray-800 py-2">Version</th>
                  <th className="border-b border-gray-800 py-2">Date</th>
                  <th className="border-b border-gray-800 py-2">Status</th>
                  <th className="border-b border-gray-800 py-2">Rating</th>
                  <th className="border-b border-gray-800 py-2 text-right">Source Score</th>
                  <th className="border-b border-gray-800 py-2 text-right">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {thesisHistory.map((tv: ResearchThesisVersion) => (
                  <tr key={tv.id} className="border-b border-gray-900 last:border-0">
                    <td className="py-3 font-semibold text-teal-300">v{tv.version}</td>
                    <td className="py-3 text-gray-400">{tv.created_at.split('T')[0]}</td>
                    <td className="py-3 text-gray-300">{tv.status}</td>
                    <td className="py-3 text-gray-300">{tv.rating}</td>
                    <td className="py-3 text-right text-gray-400">{tv.source_coverage_score}</td>
                    <td className="py-3 text-right text-gray-400">{tv.data_confidence_score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}

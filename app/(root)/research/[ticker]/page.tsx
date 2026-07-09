import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  ArrowLeft,
  BarChart3,
  BrainCircuit,
  CheckCircle2,
  Database,
  FileText,
  GitBranch,
  MessageSquare,
  Plus,
  RefreshCcw,
  ShieldCheck,
  Sigma,
  TriangleAlert,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  addResearchClaimEvidence,
  askResearchCompanyChat,
  createResearchThesisChange,
  createResearchClaim,
  createResearchMemoryItem,
  getResearchCompanyDetail,
  generateResearchThesis,
  refreshCompanyFinancials,
  refreshCompanyFinancialsSEC,
  getThesisHistory,
  type ResearchCalculatedMetric,
  type ResearchClaim,
  type ResearchChatResponse,
  type ResearchFact,
  type ResearchMemoryItem,
  type ResearchSourceDocument,
  type ResearchThesis,
  type ResearchThesisChange,
  type ResearchThesisSection,
  type ResearchThesisVersion,
  type ResearchValuation,
} from '@/lib/actions/research.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type ResearchCompanyPageProps = {
  params: Promise<{
    ticker: string;
  }>;
  searchParams: Promise<{
    chat?: string;
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

function CalculatedMetricsTable({ metrics }: { metrics: ResearchCalculatedMetric[] }) {
  if (!metrics.length) {
    return (
      <div className="rounded-md border border-gray-800 p-4 text-sm text-gray-400">
        No hay metricas calculadas todavia.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[920px] text-left text-sm">
        <thead className="text-xs uppercase text-gray-500">
          <tr>
            <th className="border-b border-gray-800 py-2">Metric</th>
            <th className="border-b border-gray-800 py-2 text-right">Value</th>
            <th className="border-b border-gray-800 py-2">Status</th>
            <th className="border-b border-gray-800 py-2">Formula</th>
            <th className="border-b border-gray-800 py-2">Period</th>
            <th className="border-b border-gray-800 py-2">Fact IDs</th>
            <th className="border-b border-gray-800 py-2 text-right">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric) => {
            const value = metric.value == null ? null : numberValue(metric.value);
            return (
              <tr key={`${metric.metric}-${metric.definition_version}-${metric.period}`} className="border-b border-gray-900 last:border-0">
                <td className="py-3 font-semibold text-gray-200">{metric.metric}</td>
                <td className="py-3 text-right text-gray-300">
                  {value == null ? 'N/A' : metric.unit === 'decimal' ? pct(value) : `${value.toFixed(2)}${metric.unit}`}
                </td>
                <td className="py-3">
                  <Badge
                    className={
                      metric.status === 'ok'
                        ? 'border-teal-800 bg-teal-950/30 text-teal-200'
                        : 'border-amber-800 bg-amber-950/30 text-amber-200'
                    }
                    variant="outline"
                  >
                    {metric.status}
                  </Badge>
                </td>
                <td className="max-w-[320px] py-3 text-xs leading-5 text-gray-400">{metric.formula}</td>
                <td className="py-3 text-gray-500">{metric.period}</td>
                <td className="py-3 text-gray-500">{metric.source_fact_ids.join(', ') || 'missing'}</td>
                <td className="py-3 text-right text-gray-400">{pct(numberValue(metric.confidence))}</td>
              </tr>
            );
          })}
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

function ClaimStatusBadge({ status }: { status: string }) {
  const isSupported = status === 'supported';
  const isContradicted = status === 'contradicted';
  const className = isContradicted
    ? 'border-red-800 bg-red-950/30 text-red-200'
    : isSupported
      ? 'border-teal-800 bg-teal-950/30 text-teal-200'
      : 'border-amber-800 bg-amber-950/30 text-amber-200';

  return (
    <Badge className={className} variant="outline">
      {isSupported ? <CheckCircle2 className="h-3 w-3" /> : null}
      {isContradicted ? <TriangleAlert className="h-3 w-3" /> : null}
      {status}
    </Badge>
  );
}

function ClaimsMemoryPanel({
  ticker,
  claims,
  sections,
  memoryItems,
  sourceDocuments,
}: {
  ticker: string;
  claims: ResearchClaim[];
  sections: ResearchThesisSection[];
  memoryItems: ResearchMemoryItem[];
  sourceDocuments: ResearchSourceDocument[];
}) {
  const sourceChunks = sourceDocuments.flatMap((document) => document.chunks ?? []);

  return (
    <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
      <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
        <div className="mb-4 flex items-center gap-2">
          <BrainCircuit className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Claims</h2>
          <span className="ml-auto text-sm text-gray-500">{claims.length}</span>
        </div>
        <form action={createResearchClaim.bind(null, ticker)} className="mb-4 grid gap-3 md:grid-cols-[1fr_150px_96px_auto]">
          <Input aria-label="Claim" name="statement" placeholder="Material claim" required />
          <Input aria-label="Claim type" defaultValue="thesis" name="claim_type" />
          <Input aria-label="Materiality" defaultValue="5" max="10" min="0" name="materiality_score" type="number" />
          <Button type="submit" variant="outline">
            <Plus className="h-4 w-4" />
            Add
          </Button>
        </form>
        <div className="space-y-3">
          {claims.length ? (
            claims.map((claim) => (
              <div key={claim.id} className="rounded-md border border-gray-800 p-3">
                <div className="flex flex-wrap items-start gap-2">
                  <ClaimStatusBadge status={claim.status} />
                  <Badge className="border-gray-700 bg-gray-900 text-gray-300" variant="outline">
                    {claim.claim_type}
                  </Badge>
                  <span className="ml-auto text-xs text-gray-500">M{claim.materiality_score}</span>
                </div>
                <p className="mt-2 text-sm leading-6 text-gray-300">{claim.statement}</p>
                <div className="mt-2 text-xs text-gray-500">
                  Evidence: {claim.evidence.length} - Confidence: {pct(numberValue(claim.confidence))}
                </div>
                {claim.evidence.length ? (
                  <div className="mt-3 space-y-2 border-t border-gray-800 pt-3">
                    {claim.evidence.slice(0, 2).map((evidence) => (
                      <div key={evidence.id} className="text-xs leading-5 text-gray-400">
                        <span className={evidence.evidence_type === 'contradicts' ? 'text-red-300' : 'text-teal-300'}>
                          {evidence.evidence_type}
                        </span>
                        {' - '}
                        {evidence.summary}
                        {evidence.document_chunk_id ? (
                          <span className="text-gray-600"> - chunk #{evidence.document_chunk_id}</span>
                        ) : evidence.document_id ? (
                          <span className="text-gray-600"> - document #{evidence.document_id}</span>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
                <form action={addResearchClaimEvidence.bind(null, ticker, claim.id)} className="mt-3 grid gap-2 border-t border-gray-800 pt-3">
                  <div className="grid gap-2 md:grid-cols-[120px_1fr]">
                    <select
                      aria-label="Evidence type"
                      className="h-10 rounded-lg border border-gray-700 bg-transparent px-3 text-sm text-gray-100"
                      name="evidence_type"
                    >
                      <option className="bg-[#111111]" value="supports">supports</option>
                      <option className="bg-[#111111]" value="contradicts">contradicts</option>
                    </select>
                    <Input aria-label="Evidence summary" name="summary" placeholder="Evidence summary" />
                  </div>
                  <div className="grid gap-2 md:grid-cols-[1fr_130px_auto]">
                    <Input aria-label="Source URL" name="source_url" placeholder="Source URL" type="url" />
                    <Input aria-label="Source tier" defaultValue="secondary" name="source_tier" />
                    <Button type="submit" variant="outline">
                      <Plus className="h-4 w-4" />
                      Evidence
                    </Button>
                  </div>
                  {sourceDocuments.length ? (
                    <div>
                      <select
                        aria-label="Evidence source"
                        className="h-10 rounded-lg border border-gray-700 bg-transparent px-3 text-sm text-gray-100"
                        name="source_ref"
                      >
                        <option className="bg-[#111111]" value="">No linked document</option>
                        {sourceDocuments.map((document) => (
                          <option key={`doc-${document.id}`} className="bg-[#111111]" value={`document:${document.id}`}>
                            Document: {document.title}
                          </option>
                        ))}
                        {sourceChunks.map((chunk) => {
                          const document = sourceDocuments.find((item) => item.id === chunk.document_id);
                          return (
                            <option key={`chunk-${chunk.id}`} className="bg-[#111111]" value={`chunk:${chunk.id}`}>
                              Chunk: {document?.title ?? `Document ${chunk.document_id}`} #{chunk.chunk_index}
                            </option>
                          );
                        })}
                      </select>
                    </div>
                  ) : null}
                </form>
              </div>
            ))
          ) : (
            <div className="rounded-md border border-gray-800 p-4 text-sm text-gray-400">No claims captured.</div>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
        <div className="mb-4 flex items-center gap-2">
          <FileText className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Memory</h2>
          <span className="ml-auto text-sm text-gray-500">{memoryItems.length}</span>
        </div>
        <form action={createResearchMemoryItem.bind(null, ticker)} className="mb-4 grid gap-3">
          <Textarea aria-label="Memory item" className="border-gray-700 bg-transparent text-gray-100" name="content" placeholder="Watch item or decision note" required />
          <div className="grid gap-3 md:grid-cols-[1fr_96px_auto]">
            <Input aria-label="Memory type" defaultValue="note" name="memory_type" />
            <Input aria-label="Importance" defaultValue="5" max="10" min="0" name="importance" type="number" />
            <Button type="submit" variant="outline">
              <Plus className="h-4 w-4" />
              Add
            </Button>
          </div>
        </form>
        <div className="space-y-3">
          {memoryItems.slice(0, 6).map((item) => (
            <div key={item.id} className="rounded-md border border-gray-800 p-3">
              <div className="flex items-center gap-2">
                <Badge className="border-gray-700 bg-gray-900 text-gray-300" variant="outline">
                  {item.memory_type}
                </Badge>
                <span className="ml-auto text-xs text-gray-500">I{item.importance}</span>
              </div>
              <p className="mt-2 text-sm leading-6 text-gray-300">{item.content}</p>
            </div>
          ))}
          {!memoryItems.length ? (
            <div className="rounded-md border border-gray-800 p-4 text-sm text-gray-400">No memory items captured.</div>
          ) : null}
        </div>
        {sections.length ? (
          <div className="mt-5 border-t border-gray-800 pt-4">
            <div className="mb-3 text-xs font-semibold uppercase text-gray-500">Thesis sections</div>
            <div className="flex flex-wrap gap-2">
              {sections.map((section) => (
                <Badge key={section.id} className="border-gray-700 bg-gray-900 text-gray-300" variant="outline">
                  {section.title}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function WhatChangedPanel({
  ticker,
  changes,
}: {
  ticker: string;
  changes: ResearchThesisChange[];
}) {
  const impactClass = (impact: string) => {
    if (impact === 'positive') return 'border-teal-800 bg-teal-950/30 text-teal-200';
    if (impact === 'negative') return 'border-red-800 bg-red-950/30 text-red-200';
    if (impact === 'mixed') return 'border-amber-800 bg-amber-950/30 text-amber-200';
    return 'border-gray-700 bg-gray-900 text-gray-300';
  };

  return (
    <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
      <div className="mb-4 flex items-center gap-2">
        <GitBranch className="h-5 w-5 text-teal-300" />
        <h2 className="text-lg font-semibold text-gray-100">What Changed</h2>
        <span className="ml-auto text-sm text-gray-500">{changes.length}</span>
      </div>
      <form action={createResearchThesisChange.bind(null, ticker)} className="mb-4 grid gap-3 xl:grid-cols-[1fr_150px_140px_96px_160px_auto]">
        <Input aria-label="Change summary" name="summary" placeholder="Thesis change" required />
        <Input aria-label="Change type" defaultValue="manual" name="change_type" />
        <select
          aria-label="Impact direction"
          className="h-10 rounded-lg border border-gray-700 bg-transparent px-3 text-sm text-gray-100"
          name="impact_direction"
        >
          <option className="bg-[#111111]" value="neutral">neutral</option>
          <option className="bg-[#111111]" value="positive">positive</option>
          <option className="bg-[#111111]" value="negative">negative</option>
          <option className="bg-[#111111]" value="mixed">mixed</option>
        </select>
        <Input aria-label="Materiality" defaultValue="5" max="10" min="0" name="materiality_score" type="number" />
        <Input aria-label="Affected metrics" name="affected_metrics" placeholder="metrics" />
        <Button type="submit" variant="outline">
          <Plus className="h-4 w-4" />
          Add
        </Button>
      </form>
      <div className="grid gap-3">
        {changes.length ? (
          changes.slice(0, 8).map((change) => (
            <div key={change.id} className="rounded-md border border-gray-800 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={impactClass(change.impact_direction)} variant="outline">
                  {change.impact_direction}
                </Badge>
                <Badge className="border-gray-700 bg-gray-900 text-gray-300" variant="outline">
                  {change.change_type}
                </Badge>
                {change.requires_review ? (
                  <Badge className="border-amber-800 bg-amber-950/30 text-amber-200" variant="outline">
                    review
                  </Badge>
                ) : null}
                <span className="ml-auto text-xs text-gray-500">M{change.materiality_score}</span>
              </div>
              <p className="mt-2 text-sm leading-6 text-gray-300">{change.summary}</p>
              <div className="mt-2 text-xs text-gray-500">
                Claims: {change.affected_claim_ids.length} - Metrics: {change.affected_metrics.join(', ') || 'none'}
              </div>
            </div>
          ))
        ) : (
          <div className="rounded-md border border-gray-800 p-4 text-sm text-gray-400">No thesis changes captured.</div>
        )}
      </div>
    </section>
  );
}

function SourceAwareChatPanel({
  ticker,
  chatQuestion,
  chatResponse,
}: {
  ticker: string;
  chatQuestion: string;
  chatResponse: ResearchChatResponse | null;
}) {
  return (
    <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
      <div className="mb-4 flex items-center gap-2">
        <MessageSquare className="h-5 w-5 text-teal-300" />
        <h2 className="text-lg font-semibold text-gray-100">Company Chat</h2>
        {chatResponse?.blocked ? (
          <Badge className="ml-auto border-amber-800 bg-amber-950/30 text-amber-200" variant="outline">
            blocked
          </Badge>
        ) : null}
      </div>
      <form className="grid gap-3 md:grid-cols-[1fr_auto]" method="GET">
        <Input
          aria-label="Ask company chat"
          defaultValue={chatQuestion}
          name="chat"
          placeholder={`Ask ${ticker} with source-aware memory`}
        />
        <Button type="submit" variant="outline">
          <MessageSquare className="h-4 w-4" />
          Ask
        </Button>
      </form>
      {chatResponse ? (
        <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_320px]">
          <article className="max-h-[520px] overflow-auto rounded-md border border-gray-800 bg-black/30 p-4">
            <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6 text-gray-300">
              {chatResponse.answer}
            </pre>
          </article>
          <aside className="rounded-md border border-gray-800 bg-black/30 p-4">
            <div className="mb-3 text-xs font-semibold uppercase text-gray-500">Sources</div>
            <div className="space-y-2">
              {chatResponse.sources.slice(0, 12).map((source, index) => (
                <div key={`${source.type}-${String(source.id)}-${index}`} className="rounded-md border border-gray-800 p-2">
                  <div className="flex items-center gap-2">
                    <Badge className="border-gray-700 bg-gray-900 text-gray-300" variant="outline">
                      {source.type}
                    </Badge>
                    <span className="ml-auto text-xs text-gray-600">#{String(source.id ?? 'n/a')}</span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-gray-400">{source.title}</p>
                </div>
              ))}
              {!chatResponse.sources.length ? (
                <div className="rounded-md border border-gray-800 p-3 text-sm text-gray-400">
                  No sources returned.
                </div>
              ) : null}
            </div>
            {chatResponse.proposed_actions.length ? (
              <div className="mt-4 border-t border-gray-800 pt-3">
                <div className="mb-2 text-xs font-semibold uppercase text-gray-500">Next actions</div>
                <ul className="list-disc space-y-1 pl-4 text-xs leading-5 text-gray-400">
                  {chatResponse.proposed_actions.map((action) => (
                    <li key={action}>{action}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </aside>
        </div>
      ) : (
        <div className="mt-4 rounded-md border border-gray-800 p-4 text-sm text-gray-400">
          Ask a question to retrieve thesis, facts, claims, evidence, documents, news and memory with provenance.
        </div>
      )}
    </section>
  );
}

export default async function ResearchCompanyPage({ params, searchParams }: ResearchCompanyPageProps) {
  const { ticker } = await params;
  const { chat = '' } = await searchParams;
  const [{ company, valuation, facts, calculatedMetrics, thesis, claims, thesisSections, thesisChanges, memoryItems, sourceDocuments }, thesisHistory] = await Promise.all([
    getResearchCompanyDetail(ticker),
    getThesisHistory(ticker),
  ]);

  if (!company) notFound();
  const chatResponse = chat.trim() ? await askResearchCompanyChat(company.ticker, chat) : null;

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
        <div className="mb-4 flex items-center gap-2">
          <Sigma className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Traceable Metrics</h2>
          <span className="ml-auto text-sm text-gray-500">{calculatedMetrics.length} metrics</span>
        </div>
        <CalculatedMetricsTable metrics={calculatedMetrics} />
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

      <ClaimsMemoryPanel
        claims={claims}
        memoryItems={memoryItems}
        sections={thesisSections}
        sourceDocuments={sourceDocuments}
        ticker={company.ticker}
      />

      <SourceAwareChatPanel chatQuestion={chat} chatResponse={chatResponse} ticker={company.ticker} />

      <WhatChangedPanel changes={thesisChanges} ticker={company.ticker} />

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

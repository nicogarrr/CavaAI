import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  ArrowLeft,
  BrainCircuit,
  Database,
  FileText,
  RefreshCcw,
  Search,
  ShieldCheck,
  Target,
} from 'lucide-react';

import { MutationForm } from '@/components/forms/MutationForm';
import { CompanyMarketPanel } from '@/components/research/CompanyMarketPanel';
import {
  DecisionAndRealityPanel,
  LongTermModelPanel,
} from '@/components/research/FundamentalModelPanels';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  askResearchCompanyChat,
  createResearchClaim,
  generateResearchThesis,
  getResearchChangesWorkspace,
  getResearchCompanySnapshot,
  getResearchDocumentsWorkspace,
  getResearchFinancialsWorkspace,
  getResearchLongTermModel,
  getResearchMoatWorkspace,
  getResearchPeersWorkspace,
  getResearchSourceAuditsWorkspace,
  getResearchThesisWorkspace,
  getResearchValuationWorkspace,
  importResearchDocumentFile,
  importResearchDocumentUrl,
  refreshCompanyFinancials,
  refreshCompanyFinancialsSEC,
  refreshCompanyResearchModel,
  type ResearchCalculatedMetric,
  type ResearchFact,
  type ResearchLongTermModel,
  type ResearchValuation,
} from '@/lib/actions/research.actions';
import { getCompanyMarketSnapshot } from '@/lib/actions/market-workspace.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const views = [
  ['overview', 'Overview'],
  ['thesis', 'Thesis'],
  ['changes', 'What Changed'],
  ['financials', 'Financials'],
  ['model', 'Long-Term Model'],
  ['market-opportunity', 'Market Opportunity'],
  ['moat', 'Moat'],
  ['peers', 'Peers'],
  ['valuation', 'Valuation'],
  ['documents', 'Documents'],
  ['sources', 'Sources'],
  ['chat', 'Chat'],
] as const;

type View = (typeof views)[number][0];

type PageProps = {
  params: Promise<{ ticker: string }>;
  searchParams: Promise<{ view?: string; chat?: string }>;
};

function asView(value: string | undefined): View {
  return views.some(([key]) => key === value) ? (value as View) : 'overview';
}

function number(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function money(value: number | string | null | undefined, currency = 'USD') {
  const parsed = number(value);
  if (parsed === null) return 'N/A';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(parsed);
}

function metricValue(value: number | string | null | undefined, unit: string) {
  const parsed = number(value);
  if (parsed === null) return 'unknown';
  if (unit === 'decimal') return `${(parsed * 100).toFixed(1)}%`;
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(parsed);
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
      <h2 className="text-lg font-semibold text-gray-100">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-dashed border-gray-800 p-6 text-sm text-gray-500">{children}</p>;
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-[#101010] p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-gray-100">{value}</div>
    </div>
  );
}

function FactTable({ facts }: { facts: ResearchFact[] }) {
  if (!facts.length) return <Empty>No persisted financial facts yet.</Empty>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-500">
          <tr>
            <th className="border-b border-gray-800 py-2">Metric</th>
            <th className="border-b border-gray-800 py-2">Period</th>
            <th className="border-b border-gray-800 py-2 text-right">Value</th>
            <th className="border-b border-gray-800 py-2 text-right">Source</th>
          </tr>
        </thead>
        <tbody>
          {facts.map((fact) => (
            <tr key={fact.id} className="text-gray-300">
              <td className="border-b border-gray-900 py-2 font-medium">{fact.metric}</td>
              <td className="border-b border-gray-900 py-2">{fact.period}</td>
              <td className="border-b border-gray-900 py-2 text-right">{metricValue(fact.value, fact.unit)}</td>
              <td className="border-b border-gray-900 py-2 text-right text-xs text-gray-500">{fact.source_type}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MetricsGrid({ metrics }: { metrics: ResearchCalculatedMetric[] }) {
  if (!metrics.length) return <Empty>Calculated metrics have not been refreshed.</Empty>;
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {metrics.map((metric) => (
        <div className="rounded-lg border border-gray-800 p-4" key={`${metric.metric}-${metric.period}-${metric.definition_version}`}>
          <div className="flex items-center justify-between gap-3">
            <span className="font-medium text-gray-200">{metric.metric}</span>
            <Badge variant="outline">{metric.status}</Badge>
          </div>
          <div className="mt-2 text-xl text-teal-300">{metricValue(metric.value, metric.unit)}</div>
          <div className="mt-2 text-xs text-gray-500">{metric.period} · {metric.definition_version}</div>
          <div className="mt-2 text-xs text-gray-600">{metric.formula}</div>
        </div>
      ))}
    </div>
  );
}

function ValuationView({ valuation, currency }: { valuation: ResearchValuation | null; currency: string }) {
  if (!valuation) return <Empty>No persisted valuation is available.</Empty>;
  if (valuation.status === 'insufficient_data') {
    return (
      <div className="rounded-lg border border-amber-900/70 bg-amber-950/20 p-4 text-sm text-amber-200">
        Valuation is blocked by missing inputs: {(valuation.missing_inputs ?? []).join(', ') || 'unspecified inputs'}.
      </div>
    );
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Stat label="Current price" value={money(valuation.current_price, currency)} />
      <Stat label="Bear" value={money(valuation.bear_value, currency)} />
      <Stat label="Base" value={money(valuation.base_value, currency)} />
      <Stat label="Bull" value={money(valuation.bull_value, currency)} />
    </div>
  );
}

function MarketOpportunityView({ model }: { model: ResearchLongTermModel | null }) {
  if (!model || model.status === 'not_generated') return <Empty>Generate the Long-Term Model before assessing market opportunity.</Empty>;
  const opportunity = model.market_opportunity;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <Stat label="TAM" value={metricValue(opportunity.top_down.tam.value, opportunity.top_down.tam.unit)} />
        <Stat label="SAM" value={metricValue(opportunity.top_down.sam.value, opportunity.top_down.sam.unit)} />
        <Stat label="SOM" value={metricValue(opportunity.top_down.som.value, opportunity.top_down.som.unit)} />
      </div>
      <Panel title="Constraint-aware verdict">
        <div className="flex flex-wrap gap-2">
          <Badge>{opportunity.verdict.label}</Badge>
          <Badge variant="outline">confidence: {opportunity.verdict.confidence}</Badge>
          <Badge variant="outline">binding: {opportunity.constraints.binding_constraint ?? 'unknown'}</Badge>
        </div>
        <p className="mt-3 text-sm text-gray-300">{opportunity.verdict.conclusion}</p>
      </Panel>
      <Panel title="Bottom-up formulas">
        <div className="space-y-3">
          {opportunity.bottom_up.formulas.map((formula) => (
            <div className="rounded-lg border border-gray-800 p-3" key={formula.label}>
              <div className="flex justify-between gap-4 text-sm">
                <span className="text-gray-200">{formula.label}</span>
                <span className="text-teal-300">{formula.value === null ? formula.status : metricValue(formula.value, 'USD')}</span>
              </div>
              {formula.missing_inputs?.length ? <p className="mt-2 text-xs text-amber-300">Missing: {formula.missing_inputs.join(', ')}</p> : null}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

export default async function ResearchCompanyPage({ params, searchParams }: PageProps) {
  const [{ ticker: rawTicker }, query] = await Promise.all([params, searchParams]);
  const ticker = rawTicker.trim().toUpperCase();
  const activeView = asView(query.view);
  const snapshot = await getResearchCompanySnapshot(ticker);
  if (!snapshot) notFound();

  const company = snapshot.company;
  let content: React.ReactNode;

  if (activeView === 'overview') {
    const market = await getCompanyMarketSnapshot(ticker);
    content = (
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Research health" value={`${snapshot.research_health.score}/100`} />
          <Stat label="Facts" value={snapshot.counts.facts} />
          <Stat label="Claims" value={snapshot.counts.claims} />
          <Stat label="Documents" value={snapshot.counts.documents} />
        </div>
        <div className="grid gap-6 xl:grid-cols-2">
          <Panel title="Latest thesis">
            {snapshot.latest_thesis ? (
              <>
                <div className="flex flex-wrap gap-2">
                  <Badge>{snapshot.latest_thesis.rating}</Badge>
                  <Badge variant="outline">v{snapshot.latest_thesis.version}</Badge>
                  <Badge variant="outline">{snapshot.latest_thesis.status}</Badge>
                </div>
                <p className="mt-3 text-sm leading-6 text-gray-300">{snapshot.latest_thesis.executive_summary}</p>
              </>
            ) : <Empty>No thesis has been generated.</Empty>}
          </Panel>
          <Panel title="Long-Term Fundamental Model">
            {snapshot.model_summary ? (
              <div className="space-y-3 text-sm text-gray-300">
                <div className="flex flex-wrap gap-2">
                  <Badge>{snapshot.model_summary.framework_key}</Badge>
                  <Badge variant="outline">v{snapshot.model_summary.version}</Badge>
                  <Badge variant="outline">{snapshot.model_summary.publishable ? 'publishable' : 'blocked'}</Badge>
                </div>
                <p>{snapshot.model_summary.engine_version} · {snapshot.model_summary.horizon_years} years</p>
              </div>
            ) : <Empty>No persisted model. Generate it explicitly from the model tab.</Empty>}
          </Panel>
        </div>
        {snapshot.research_health.missing?.length ? (
          <div className="rounded-lg border border-amber-900/60 bg-amber-950/20 p-4 text-sm text-amber-200">
            Missing research layers: {snapshot.research_health.missing.join(', ')}
          </div>
        ) : null}
        <CompanyMarketPanel snapshot={market} />
      </div>
    );
  } else if (activeView === 'thesis') {
    const data = await getResearchThesisWorkspace(ticker);
    content = (
      <div className="space-y-6">
        <div className="flex flex-wrap gap-3">
          <MutationForm action={generateResearchThesis.bind(null, ticker)} successMessage="New thesis version generated">
            <Button type="submit"><BrainCircuit className="mr-2 h-4 w-4" />Generate thesis</Button>
          </MutationForm>
          <Badge variant="outline">{data.history.length} versions</Badge>
          <Badge variant="outline">{data.claims.length} claims</Badge>
        </div>
        <Panel title="Current thesis">
          {data.thesis ? (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2"><Badge>{data.thesis.rating}</Badge><Badge variant="outline">{data.thesis.status}</Badge></div>
              <p className="text-sm leading-6 text-gray-300">{data.thesis.executive_summary}</p>
              <div className="whitespace-pre-wrap rounded-lg border border-gray-800 bg-black/20 p-4 text-sm leading-6 text-gray-400">{data.thesis.thesis_markdown}</div>
            </div>
          ) : <Empty>No thesis exists.</Empty>}
        </Panel>
        <Panel title="Company-specific thesis sections">
          <div className="grid gap-3 lg:grid-cols-2">
            {data.sections.map((section) => (
              <div className="rounded-lg border border-gray-800 p-4" key={section.id}>
                <div className="flex justify-between gap-3"><h3 className="font-medium text-gray-200">{section.title}</h3><Badge variant="outline">{section.status}</Badge></div>
                <p className="mt-2 text-sm leading-6 text-gray-400">{section.body}</p>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Claims and evidence">
          <MutationForm action={createResearchClaim.bind(null, ticker)} className="mb-5 grid gap-3 md:grid-cols-[1fr_150px_auto]" resetOnSuccess successMessage="Claim created">
            <Textarea name="statement" placeholder="A falsifiable company-specific claim" required />
            <Input name="materiality_score" type="number" min="0" max="10" defaultValue="5" />
            <Button type="submit">Add claim</Button>
          </MutationForm>
          <div className="space-y-3">
            {data.claims.length ? data.claims.map((claim) => (
              <div className="rounded-lg border border-gray-800 p-4" key={claim.id}>
                <div className="flex flex-wrap gap-2"><Badge variant="outline">{claim.status}</Badge><Badge variant="outline">materiality {claim.materiality_score}</Badge><Badge variant="outline">{claim.evidence.length} evidence</Badge></div>
                <p className="mt-3 text-sm text-gray-300">{claim.statement}</p>
              </div>
            )) : <Empty>No claims recorded.</Empty>}
          </div>
        </Panel>
        <Panel title="Dependency graph and red team">
          <p className="text-sm text-gray-300">{data.graph ? `${data.graph.nodes.length} nodes · ${data.graph.edges.length} dependencies` : 'No persisted graph.'}</p>
          <p className="mt-2 text-sm text-gray-400">{data.redTeam?.strongest_bear_case ?? 'No red-team run persisted.'}</p>
        </Panel>
      </div>
    );
  } else if (activeView === 'changes') {
    const data = await getResearchChangesWorkspace(ticker);
    content = (
      <div className="space-y-6">
        <Panel title="What Changed">
          <div className="space-y-3">
            {data.changes.length ? data.changes.map((change) => (
              <div className="rounded-lg border border-gray-800 p-4" key={change.id}>
                <div className="flex flex-wrap gap-2"><Badge>{change.impact_direction}</Badge><Badge variant="outline">{change.change_type}</Badge><Badge variant="outline">materiality {change.materiality_score}</Badge></div>
                <p className="mt-3 text-sm text-gray-300">{change.summary}</p>
              </div>
            )) : <Empty>No material changes recorded.</Empty>}
          </div>
        </Panel>
        <div className="grid gap-6 xl:grid-cols-2">
          <Panel title="Open reviews"><div className="space-y-2">{data.reviews.length ? data.reviews.map((review) => <div className="rounded-lg border border-gray-800 p-3 text-sm text-gray-300" key={review.id}>{review.title}</div>) : <Empty>No open reviews.</Empty>}</div></Panel>
          <Panel title="Alerts"><div className="space-y-2">{data.alerts.length ? data.alerts.map((alert) => <div className="rounded-lg border border-gray-800 p-3 text-sm" key={alert.id}><Badge variant="outline">{alert.severity}</Badge><p className="mt-2 text-gray-300">{alert.message}</p></div>) : <Empty>No alerts.</Empty>}</div></Panel>
        </div>
        <DecisionAndRealityPanel ticker={ticker} decisions={data.decisions} reviews={data.expectations} />
      </div>
    );
  } else if (activeView === 'financials') {
    const data = await getResearchFinancialsWorkspace(ticker);
    content = (
      <div className="space-y-6">
        <div className="flex flex-wrap gap-3">
          <MutationForm action={refreshCompanyFinancials.bind(null, ticker)} successMessage="FMP financials refreshed"><Button type="submit" variant="outline">Refresh FMP</Button></MutationForm>
          <MutationForm action={refreshCompanyFinancialsSEC.bind(null, ticker)} successMessage="SEC financials refreshed"><Button type="submit" variant="outline">Refresh SEC</Button></MutationForm>
          <MutationForm action={refreshCompanyResearchModel.bind(null, ticker)} successMessage="Metrics and research model refreshed"><Button type="submit"><RefreshCcw className="mr-2 h-4 w-4" />Recalculate</Button></MutationForm>
        </div>
        <Panel title="Traceable calculated metrics"><MetricsGrid metrics={data.calculatedMetrics} /></Panel>
        <Panel title="Canonical financial facts"><FactTable facts={data.facts} /></Panel>
      </div>
    );
  } else if (activeView === 'model') {
    const model = await getResearchLongTermModel(ticker);
    content = (
      <div className="space-y-5">
        <MutationForm action={refreshCompanyResearchModel.bind(null, ticker)} successMessage="Long-Term Model generated"><Button type="submit"><RefreshCcw className="mr-2 h-4 w-4" />Generate model</Button></MutationForm>
        <LongTermModelPanel model={model?.status === 'not_generated' ? null : model} />
      </div>
    );
  } else if (activeView === 'market-opportunity') {
    content = <MarketOpportunityView model={await getResearchLongTermModel(ticker)} />;
  } else if (activeView === 'moat') {
    const moat = await getResearchMoatWorkspace(ticker);
    content = (
      <div className="space-y-5">
        <MutationForm action={refreshCompanyResearchModel.bind(null, ticker)} successMessage="Moat assessment refreshed"><Button type="submit" variant="outline"><ShieldCheck className="mr-2 h-4 w-4" />Refresh evidence assessment</Button></MutationForm>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {moat?.moats.length ? moat.moats.map((item) => <div className="rounded-xl border border-gray-800 bg-[#101010] p-4" key={item.type}><div className="flex justify-between gap-3"><span className="font-medium text-gray-200">{item.type.replaceAll('_', ' ')}</span><Badge>{item.strength}/100</Badge></div><p className="mt-3 text-sm text-gray-400">{item.status} · {item.trend} · persistence {item.persistence}</p><p className="mt-2 text-xs text-gray-600">{item.supporting_claim_ids.length} supporting · {item.contradicting_claim_ids.length} contradicting claims</p></div>) : <Empty>No persisted moat assessment.</Empty>}
        </div>
      </div>
    );
  } else if (activeView === 'peers') {
    const peers = await getResearchPeersWorkspace(ticker);
    content = (
      <div className="space-y-6">
        <Panel title="Peer set"><p className="text-sm text-gray-300">{peers.comparison?.basis ?? 'No peer set'} · {peers.comparison?.peer_count ?? 0} peers</p><div className="mt-4 flex flex-wrap gap-2">{peers.comparison?.companies.map((peer) => <Badge variant={peer.is_target ? 'default' : 'outline'} key={peer.ticker}>{peer.ticker}</Badge>)}</div></Panel>
        <Panel title="Comparable benchmarks"><div className="grid gap-3 md:grid-cols-2">{Object.entries(peers.comparison?.benchmarks ?? {}).map(([metric, value]) => <div className="rounded-lg border border-gray-800 p-3" key={metric}><div className="text-sm text-gray-200">{metric}</div><div className="mt-2 text-xs text-gray-500">Target {value.target_value ?? 'unknown'} · median {value.peer_median ?? 'unknown'} · n={value.peer_sample_size}</div></div>)}</div></Panel>
        <Panel title="Advantages and disadvantages"><p className="text-sm text-gray-400">{peers.analysis?.methodology ?? 'No persisted peer analysis.'}</p><p className="mt-3 text-xs text-amber-300">{peers.analysis?.insufficient_data.join(', ')}</p></Panel>
      </div>
    );
  } else if (activeView === 'valuation') {
    content = <ValuationView valuation={await getResearchValuationWorkspace(ticker)} currency={company.currency} />;
  } else if (activeView === 'documents') {
    const documents = await getResearchDocumentsWorkspace(ticker, false);
    content = (
      <div className="space-y-6">
        <div className="grid gap-6 xl:grid-cols-2">
          <Panel title="Upload a primary source"><MutationForm action={importResearchDocumentFile} className="grid gap-3" successMessage="Document uploaded"><input type="hidden" name="ticker" value={ticker} /><Input name="title" placeholder="Document title" required /><Input name="file" type="file" required /><Button type="submit">Upload</Button></MutationForm></Panel>
          <Panel title="Import from URL"><MutationForm action={importResearchDocumentUrl} className="grid gap-3" successMessage="Document imported"><input type="hidden" name="ticker" value={ticker} /><Input name="title" placeholder="Document title" required /><Input name="url" type="url" placeholder="https://..." required /><Input name="source_type" placeholder="sec_filing / investor_relations" defaultValue="url" /><Button type="submit">Import</Button></MutationForm></Panel>
        </div>
        <Panel title="Documents"><div className="space-y-3">{documents.length ? documents.map((document) => <div className="rounded-lg border border-gray-800 p-4" key={document.id}><div className="flex flex-wrap items-center gap-2"><FileText className="h-4 w-4 text-teal-300" /><span className="font-medium text-gray-200">{document.title}</span><Badge variant="outline">{document.source_tier}</Badge></div><p className="mt-2 text-xs text-gray-500">{document.source_type} · {document.published_at ?? 'date unknown'}</p></div>) : <Empty>No documents ingested.</Empty>}</div></Panel>
      </div>
    );
  } else if (activeView === 'sources') {
    const audits = await getResearchSourceAuditsWorkspace(ticker);
    content = <Panel title="Source audits"><div className="space-y-3">{audits.length ? audits.slice(0, 100).map((audit) => <div className="rounded-lg border border-gray-800 p-4" key={audit.id}><div className="flex flex-wrap gap-2"><Badge>{audit.passed ? 'passed' : 'failed'}</Badge><Badge variant="outline">coverage {audit.source_coverage_score}/100</Badge><Badge variant="outline">thesis {audit.thesis_version_id ?? 'unknown'}</Badge></div>{audit.required_fixes.length ? <p className="mt-3 text-sm text-amber-300">{audit.required_fixes.join(' · ')}</p> : null}</div>) : <Empty>No source audits persisted.</Empty>}</div></Panel>;
  } else {
    const response = query.chat ? await askResearchCompanyChat(ticker, query.chat) : null;
    content = (
      <div className="space-y-6">
        <Panel title="Source-aware company chat">
          <form className="flex gap-3" method="get"><input type="hidden" name="view" value="chat" /><Input name="chat" defaultValue={query.chat} placeholder={`Ask a source-aware question about ${ticker}`} minLength={3} required /><Button type="submit"><Search className="mr-2 h-4 w-4" />Ask</Button></form>
        </Panel>
        {response ? <Panel title="Answer"><div className="whitespace-pre-wrap text-sm leading-7 text-gray-300">{response.answer}</div><div className="mt-4 flex flex-wrap gap-2"><Badge variant="outline">model {response.model ?? 'deterministic'}</Badge><Badge variant="outline">{response.sources.length} sources</Badge><Badge variant="outline">{response.blocked ? 'insufficient data' : 'grounded'}</Badge></div></Panel> : <Empty>Ask a question to retrieve the deterministic evidence contract and source-aware synthesis.</Empty>}
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-[#080808] px-4 py-6 text-gray-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1600px]">
        <Link className="mb-5 inline-flex items-center text-sm text-gray-500 hover:text-gray-200" href="/research"><ArrowLeft className="mr-2 h-4 w-4" />Research</Link>
        <header className="mb-6 flex flex-col gap-4 border-b border-gray-800 pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-3"><h1 className="text-3xl font-bold">{ticker}</h1><Badge variant="outline">{company.exchange}</Badge><Badge variant="outline">{company.currency}</Badge></div>
            <p className="mt-2 text-gray-400">{company.name} · {company.sector} · {company.industry}</p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-gray-500"><span className="inline-flex items-center gap-1"><Database className="h-4 w-4" />read-only snapshot</span><span className="inline-flex items-center gap-1"><Target className="h-4 w-4" />{company.company_type}</span></div>
        </header>
        <nav aria-label="Research modules" className="mb-7 flex gap-2 overflow-x-auto pb-2">
          {views.map(([key, label]) => (
            <Link className={`whitespace-nowrap rounded-lg border px-3 py-2 text-sm transition ${activeView === key ? 'border-teal-600 bg-teal-950/40 text-teal-200' : 'border-gray-800 text-gray-400 hover:border-gray-700 hover:text-gray-200'}`} href={`/research/${encodeURIComponent(ticker)}?view=${key}`} key={key}>{label}</Link>
          ))}
          {[
            ['financial-terminal', 'Financial Terminal'],
            ['driver-assumptions', 'Assumptions'],
            ['decision-lessons', 'Lessons'],
            ['management-credibility', 'Management'],
          ].map(([path, label]) => (
            <Link className="whitespace-nowrap rounded-lg border border-teal-900/60 px-3 py-2 text-sm text-teal-300 transition hover:border-teal-700 hover:text-teal-200" href={`/research/${encodeURIComponent(ticker)}/${path}`} key={path}>{label}</Link>
          ))}
        </nav>
        {content}
      </div>
    </main>
  );
}

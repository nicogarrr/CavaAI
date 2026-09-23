import Link from 'next/link';
import {
  ArrowLeft,
  Database,
  FileDown,
  FileText,
  RefreshCcw,
  Search,
  ShieldCheck,
  Target,
} from 'lucide-react';

import { MoatTerm } from '@/components/GlossaryTerm';
import { MutationForm } from '@/components/forms/MutationForm';
import { FileUploadInput } from '@/components/forms/FileUploadInput';
import { CompanyMarketPanel } from '@/components/research/CompanyMarketPanel';
import CollapsiblePanel from '@/components/research/CollapsiblePanel';
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
import { getWatchlist } from '@/lib/actions/watchlist.actions';
import BackendOffline from '@/components/system/BackendOffline';
import { isBackendUnavailableError } from '@/lib/backend-offline';
import QuickAlertButton from '@/components/research/QuickAlertButton';
import ThesisMemo from '@/components/research/ThesisMemo';
import ThesisExportButtons from '@/components/research/ThesisExportButtons';
import ThesisApproveButton from '@/components/research/ThesisApproveButton';
import CitationsList from '@/components/chat/CitationsList';
import FollowButton from '@/components/screener/FollowButton';
import ThesisGenerateButton from '@/components/research/ThesisGenerateButton';
import { formatCompact, formatDate, formatDateTime, formatMoney, formatPercent } from '@/lib/format';
import { glossary, moatGlossaryKey } from '@/lib/glossary';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const views = [
  ['overview', 'Resumen'],
  ['thesis', 'Tesis'],
  ['changes', 'Qué ha cambiado'],
  ['financials', 'Financieros'],
  ['model', 'Modelo a largo plazo'],
  ['market-opportunity', 'Oportunidad de mercado'],
  ['moat', 'Foso'],
  ['peers', 'Comparables'],
  ['valuation', 'Valoración'],
  ['documents', 'Documentos'],
  ['sources', 'Fuentes'],
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

/** Etiquetas en español para enums persistidos por el backend */
const STATUS_LABELS: Record<string, string> = {
  draft: 'borrador',
  review: 'en revisión',
  approved: 'aprobada',
  published: 'publicada',
  rejected: 'rechazada',
  stale: 'desactualizada',
  proposed: 'propuesta',
  supported: 'respaldada',
  refuted: 'refutada',
  open: 'abierta',
  available: 'disponible',
  partial: 'parcial',
  missing: 'faltante',
  blocked: 'bloqueada',
  insufficient_data: 'datos insuficientes',
  positive: 'positivo',
  negative: 'negativo',
  neutral: 'neutral',
  up: 'al alza',
  down: 'a la baja',
  operating_company: 'empresa operativa',
  fund: 'fondo',
  etf: 'ETF',
  trust: 'trust',
  rising: 'al alza',
  falling: 'a la baja',
  stable: 'estable',
};

const RATING_LABELS: Record<string, string> = {
  buy: 'compra',
  accumulate: 'acumular',
  overweight: 'sobreponderar',
  hold: 'mantener',
  underweight: 'infraponderar',
  trim: 'recortar',
  sell: 'venta',
  avoid: 'evitar',
  watch: 'seguimiento',
};

function label(value: string | null | undefined): string {
  if (!value) return '—';
  return STATUS_LABELS[value] ?? RATING_LABELS[value] ?? value.replaceAll('_', ' ');
}

/** Definición metodológica del foso (glosario compartido) para pintarla en la card */
function moatDefinition(type: string): string | null {
  const key = moatGlossaryKey[type];
  return key ? glossary[key].short : null;
}

function metricValue(value: number | string | null | undefined, unit: string) {
  const parsed = number(value);
  if (parsed === null) return 'desconocido';
  if (unit === 'decimal') return formatPercent(parsed);
  return formatCompact(parsed);
}

function Panel({ title, children, collapsibleOnMobile = false }: { title: string; children: React.ReactNode; collapsibleOnMobile?: boolean }) {
  if (collapsibleOnMobile) {
    return <CollapsiblePanel title={title}>{children}</CollapsiblePanel>;
  }
  return (
    <section className="rounded-xl border border-gray-800 bg-[#101010] p-4 sm:p-5">
      <h2 className="text-lg font-semibold text-gray-100">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

/**
 * Estado vacío honesto con CTA: el usuario siempre tiene un primer paso
 * concreto (importar fuentes, generar el modelo, crear la tesis).
 */
function Empty({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-gray-800 p-6 text-sm text-gray-500">
      <p>{children}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

/** Enlace-CTA estándar de los estados vacíos ("primer paso") */
function EmptyLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      className="inline-flex items-center gap-2 rounded-md border border-teal-800 px-3 py-2 text-xs font-medium text-teal-300 transition hover:border-teal-600 hover:text-teal-200"
      href={href}
    >
      {children}
    </Link>
  );
}

function Stat({ label: statLabel, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-[#101010] p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">{statLabel}</div>
      <div className="mt-2 text-2xl font-semibold text-gray-100">{value}</div>
    </div>
  );
}

function FactCard({ fact }: { fact: ResearchFact }) {
  return (
    <div className="rounded-lg border border-gray-800 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-gray-200">{fact.metric}</span>
        <span className="text-sm font-semibold text-teal-300">{metricValue(fact.value, fact.unit)}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-2 text-xs text-gray-500">
        <span>{fact.period}</span>
        <span>·</span>
        <span>{label(fact.source_type)}</span>
      </div>
    </div>
  );
}

/** Hechos visibles en móvil antes del «ver más» */
const FACTS_MOBILE_PAGE = 10;

function FactTable({ facts, ticker }: { facts: ResearchFact[]; ticker: string }) {
  if (!facts.length) {
    return (
      <Empty action={<EmptyLink href={`/research/${encodeURIComponent(ticker)}?view=documents`}>Importa una fuente primaria</EmptyLink>}>
        Todavía no hay hechos financieros persistidos.
      </Empty>
    );
  }
  return (
    <>
      {/* Móvil: cards paginadas con «ver más» en vez de corte silencioso */}
      <div className="space-y-3 md:hidden">
        {facts.slice(0, FACTS_MOBILE_PAGE).map((fact) => (
          <FactCard key={fact.id} fact={fact} />
        ))}
        {facts.length > FACTS_MOBILE_PAGE ? (
          <details className="rounded-lg border border-gray-800 p-3">
            <summary className="cursor-pointer text-sm font-medium text-teal-300">
              Ver más ({facts.length - FACTS_MOBILE_PAGE} restantes)
            </summary>
            <div className="mt-3 space-y-3">
              {facts.slice(FACTS_MOBILE_PAGE).map((fact) => (
                <FactCard key={fact.id} fact={fact} />
              ))}
            </div>
          </details>
        ) : null}
      </div>
      {/* Escritorio: tabla completa */}
      <div className="hidden overflow-x-auto md:block">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-500">
          <tr>
            <th className="border-b border-gray-800 py-2">Métrica</th>
            <th className="border-b border-gray-800 py-2">Periodo</th>
            <th className="border-b border-gray-800 py-2 text-right">Valor</th>
            <th className="border-b border-gray-800 py-2 text-right">Fuente</th>
          </tr>
        </thead>
        <tbody>
          {facts.map((fact) => (
            <tr key={fact.id} className="text-gray-300">
              <td className="border-b border-gray-900 py-2 font-medium">{fact.metric}</td>
              <td className="border-b border-gray-900 py-2">{fact.period}</td>
              <td className="border-b border-gray-900 py-2 text-right">{metricValue(fact.value, fact.unit)}</td>
              <td className="border-b border-gray-900 py-2 text-right text-xs text-gray-500">{label(fact.source_type)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </>
  );
}

function MetricsGrid({ metrics, ticker }: { metrics: ResearchCalculatedMetric[]; ticker: string }) {
  if (!metrics.length) {
    return (
      <Empty action={<EmptyLink href={`/research/${encodeURIComponent(ticker)}?view=documents`}>Añade documentos y recalcula</EmptyLink>}>
        Las métricas calculadas aún no se han refrescado.
      </Empty>
    );
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {metrics.map((metric) => (
        <div className="rounded-lg border border-gray-800 p-4" key={`${metric.metric}-${metric.period}-${metric.definition_version}`}>
          <div className="flex items-center justify-between gap-3">
            <span className="font-medium text-gray-200">{metric.metric}</span>
            <Badge variant="outline">{label(metric.status)}</Badge>
          </div>
          <div className="mt-2 text-xl text-teal-300">{metricValue(metric.value, metric.unit)}</div>
          <div className="mt-2 text-xs text-gray-500">{metric.period} · {metric.definition_version}</div>
          <div className="mt-2 text-xs text-gray-600">{metric.formula}</div>
        </div>
      ))}
    </div>
  );
}

function ValuationView({ valuation, currency, ticker }: { valuation: ResearchValuation | null; currency: string; ticker: string }) {
  if (!valuation) {
    return (
      <Empty action={<EmptyLink href={`/research/${encodeURIComponent(ticker)}?view=model`}>Genera primero el modelo a largo plazo</EmptyLink>}>
        No hay ninguna valoración persistida.
      </Empty>
    );
  }
  if (valuation.status === 'insufficient_data') {
    return (
      <div className="rounded-lg border border-amber-900/70 bg-amber-950/20 p-4 text-sm text-amber-200">
        La valoración está bloqueada por entradas faltantes: {(valuation.missing_inputs ?? []).join(', ') || 'entradas sin especificar'}.
      </div>
    );
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Stat label="Precio actual" value={formatMoney(valuation.current_price, currency)} />
      <Stat label="Bear" value={formatMoney(valuation.bear_value, currency)} />
      <Stat label="Base" value={formatMoney(valuation.base_value, currency)} />
      <Stat label="Bull" value={formatMoney(valuation.bull_value, currency)} />
    </div>
  );
}

function MarketOpportunityView({ model, ticker }: { model: ResearchLongTermModel | null; ticker: string }) {
  if (!model || model.status === 'not_generated') {
    return (
      <Empty action={<EmptyLink href={`/research/${encodeURIComponent(ticker)}?view=model`}>Generar el modelo a largo plazo</EmptyLink>}>
        Genera el modelo a largo plazo antes de valorar la oportunidad de mercado.
      </Empty>
    );
  }
  const opportunity = model.market_opportunity;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <Stat label="TAM (mercado total)" value={metricValue(opportunity.top_down.tam.value, opportunity.top_down.tam.unit)} />
        <Stat label="SAM (mercado atendible)" value={metricValue(opportunity.top_down.sam.value, opportunity.top_down.sam.unit)} />
        <Stat label="SOM (mercado obtenible)" value={metricValue(opportunity.top_down.som.value, opportunity.top_down.som.unit)} />
      </div>
      <Panel title="Veredicto con restricciones">
        <div className="flex flex-wrap gap-2">
          <Badge>{label(opportunity.verdict.label)}</Badge>
          <Badge variant="outline">confianza: {label(opportunity.verdict.confidence)}</Badge>
          <Badge variant="outline">restricción ligante: {opportunity.constraints.binding_constraint ? label(opportunity.constraints.binding_constraint) : 'desconocida'}</Badge>
        </div>
        <p className="mt-3 text-sm text-gray-300">{opportunity.verdict.conclusion}</p>
      </Panel>
      <Panel title="Fórmulas bottom-up">
        <div className="space-y-3">
          {opportunity.bottom_up.formulas.map((formula) => (
            <div className="rounded-lg border border-gray-800 p-3" key={formula.label}>
              <div className="flex justify-between gap-4 text-sm">
                <span className="text-gray-200">{formula.label}</span>
                <span className="text-teal-300">{formula.value === null ? label(formula.status) : metricValue(formula.value, 'USD')}</span>
              </div>
              {formula.missing_inputs?.length ? <p className="mt-2 text-xs text-amber-300">Faltan entradas: {formula.missing_inputs.join(', ')}</p> : null}
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
  // Snapshot (backend) y market (Finnhub: profile+quote+candles) son
  // independientes: se lanzan juntos y el coste pasa de suma a máximo.
  // market solo se consume en 'overview'; en el resto de vistas la promesa
  // ni se crea.
  const snapshotPromise = getResearchCompanySnapshot(ticker);
  const marketPromise = activeView === 'overview' ? getCompanyMarketSnapshot(ticker) : undefined;
  let snapshot: Awaited<typeof snapshotPromise>;
  try {
    snapshot = await snapshotPromise;
  } catch (error) {
    if (isBackendUnavailableError(error)) {
      return <BackendOffline feature={`Research de ${ticker}`} retryHref={`/research/${ticker}`} />;
    }
    throw error;
  }
  if (!snapshot) {
    // Ficha de la acción SIN research (aprobado por Nico 2026-09-23): los
    // datos de mercado (Finnhub) no dependen del research, así que la página
    // muestra el panel de mercado completo + estado honesto con CTA, en vez
    // del 404 pelado que veía el buscador con la BD nueva.
    let market: Awaited<ReturnType<typeof getCompanyMarketSnapshot>>;
    try {
      market = await getCompanyMarketSnapshot(ticker);
    } catch (error) {
      if (isBackendUnavailableError(error)) {
        return <BackendOffline feature={`Datos de mercado de ${ticker}`} retryHref={`/research/${ticker}`} />;
      }
      throw error;
    }
    return (
      <main className="min-h-screen bg-[#080808] px-4 py-6 text-gray-100 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[1600px] space-y-6">
          <Link className="inline-flex items-center text-sm text-gray-500 hover:text-gray-200" href="/research"><ArrowLeft className="mr-2 h-4 w-4" />Research</Link>
          <CompanyMarketPanel snapshot={market} />
          <section className="rounded-xl border border-dashed border-gray-700 bg-[#111111] p-6 text-center">
            <FileText className="mx-auto h-8 w-8 text-gray-600" />
            <h1 className="mt-3 text-lg font-semibold text-gray-100">Research aún no generado</h1>
            <p className="mx-auto mt-1 max-w-xl text-sm leading-6 text-gray-400">
              Esta empresa todavía no tiene research generado. Puedes lanzarlo ahora: el motor
              recopila evidencia con fuentes trazables y construye la tesis paso a paso
              (puede tardar unos minutos).
            </p>
            <div className="mt-4 flex justify-center">
              <ThesisGenerateButton ticker={ticker} />
            </div>
          </section>
        </div>
      </main>
    );
  }

  const company = snapshot.company;
  // Estado "seguido" real del usuario para el botón seguir/dejar de seguir.
  const watchlist = await getWatchlist();
  const isFollowed = watchlist.some((item) => item.symbol.toUpperCase() === ticker);
  let content: React.ReactNode;

  if (activeView === 'overview') {
    // marketPromise ya se lanzó en paralelo al snapshot más arriba.
    let market: Awaited<ReturnType<typeof getCompanyMarketSnapshot>>;
    try {
      market = await (marketPromise ?? getCompanyMarketSnapshot(ticker));
    } catch (error) {
      if (isBackendUnavailableError(error)) {
        return <BackendOffline feature={`Datos de mercado de ${ticker}`} retryHref={`/research/${ticker}`} />;
      }
      throw error;
    }
    content = (
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Salud del research" value={`${snapshot.research_health.score}/100`} />
          <Stat label="Hechos" value={snapshot.counts.facts} />
          <Stat label="Afirmaciones" value={snapshot.counts.claims} />
          <Stat label="Documentos" value={snapshot.counts.documents} />
        </div>
        <div className="grid gap-6 xl:grid-cols-2">
          <Panel title="Última tesis">
            {snapshot.latest_thesis ? (
              <>
                <div className="flex flex-wrap gap-2">
                  <Badge>{label(snapshot.latest_thesis.rating)}</Badge>
                  <Badge variant="outline">v{snapshot.latest_thesis.version}</Badge>
                  <Badge variant="outline">{label(snapshot.latest_thesis.status)}</Badge>
                </div>
                <p className="mt-3 text-sm leading-6 text-gray-300">{snapshot.latest_thesis.executive_summary}</p>
              </>
            ) : (
              <Empty action={<EmptyLink href={`/research/${encodeURIComponent(ticker)}?view=thesis`}>Genera la primera tesis</EmptyLink>}>
                Aún no se ha generado ninguna tesis.
              </Empty>
            )}
          </Panel>
          <Panel title="Modelo fundamental a largo plazo">
            {snapshot.model_summary ? (
              <div className="space-y-3 text-sm text-gray-300">
                <div className="flex flex-wrap gap-2">
                  <Badge>{snapshot.model_summary.framework_key}</Badge>
                  <Badge variant="outline">v{snapshot.model_summary.version}</Badge>
                  <Badge variant="outline">{snapshot.model_summary.publishable ? 'publicable' : 'bloqueado'}</Badge>
                </div>
                <p>{snapshot.model_summary.engine_version} · {snapshot.model_summary.horizon_years} años</p>
              </div>
            ) : (
              <Empty action={<EmptyLink href={`/research/${encodeURIComponent(ticker)}?view=model`}>Generar el modelo</EmptyLink>}>
                Sin modelo persistido. Genéralo de forma explícita desde la pestaña de modelo.
              </Empty>
            )}
          </Panel>
        </div>
        {snapshot.research_health.missing?.length ? (
          <div className="rounded-lg border border-amber-900/60 bg-amber-950/20 p-4 text-sm text-amber-200">
            Capas de research que faltan: {snapshot.research_health.missing.join(', ')}.
            <Link className="ml-2 underline hover:text-amber-100" href={`/research/${encodeURIComponent(ticker)}?view=documents`}>
              Importa fuentes para completarlas
            </Link>
          </div>
        ) : null}
        <CompanyMarketPanel snapshot={market} />
      </div>
    );
  } else if (activeView === 'thesis') {
    const data = await getResearchThesisWorkspace(ticker);
    content = (
      <div className="space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <ThesisGenerateButton ticker={ticker} />
          <ThesisApproveButton ticker={ticker} />
          <Link
            className="inline-flex items-center gap-2 rounded-md border border-gray-700 px-4 py-2 text-sm font-medium text-gray-200 transition hover:border-teal-700 hover:text-teal-200"
            href="/export"
          >
            <FileDown className="h-4 w-4" />Exportar journal
          </Link>
          <a
            className="inline-flex items-center gap-2 rounded-md border border-gray-700 px-4 py-2 text-sm font-medium text-gray-200 transition hover:border-teal-700 hover:text-teal-200"
            href={`/api/thesis-memo/${encodeURIComponent(ticker)}`}
          >
            <FileDown className="h-4 w-4" />Exportar memo
          </a>
          <ThesisExportButtons ticker={ticker} />
          <Badge variant="outline">{data.history.length} versiones</Badge>
          <Badge variant="outline">{data.claims.length} afirmaciones</Badge>
        </div>
        <Panel title="Historial de versiones y aprobaciones" collapsibleOnMobile>
          {data.historyDetail.history.length === 0 ? (
            <Empty>Aún no hay historial de versiones.</Empty>
          ) : (
            <div className="space-y-3">
              {data.historyDetail.history.map((entry) => (
                <div className="rounded-lg border border-gray-800 p-4" key={entry.id}>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">v{entry.version}</Badge>
                    <Badge variant={entry.status === 'published' ? 'default' : 'outline'}>{label(entry.status)}</Badge>
                    <Badge variant="outline">{label(entry.rating)}</Badge>
                    {entry.diff?.rating_changed ? <Badge>rating cambiado</Badge> : null}
                    <span className="ml-auto text-xs text-gray-500">
                      {formatDateTime(entry.updated_at)}
                    </span>
                  </div>
                  {entry.diff ? (
                    <p className="mt-2 text-sm leading-6 text-gray-400">{entry.diff.change_summary}</p>
                  ) : (
                    <p className="mt-2 text-xs text-gray-600">Primera versión registrada o sin diff persistido.</p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                    <span>red-team {entry.red_team_score}/100</span>
                    <span>confianza datos {entry.data_confidence_score}/100</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="mt-3 text-xs text-gray-600">
            El historial muestra estado, fecha y resumen del cambio tal como están persistidos; el sistema no registra quién aprobó cada versión.
          </p>
        </Panel>
        <Panel title="Tesis actual">
          {data.thesis ? (
            <ThesisMemo
              thesis={data.thesis}
              ticker={ticker}
              debateBody={
                data.sections.find((section) => section.section_key === 'thesis_debate')?.body ?? null
              }
            />
          ) : (
            <Empty action={<EmptyLink href={`/research/${encodeURIComponent(ticker)}?view=documents`}>Importa fuentes antes de generar</EmptyLink>}>
              Aún no existe ninguna tesis.
            </Empty>
          )}
        </Panel>
        <Panel title="Secciones de tesis específicas de la empresa" collapsibleOnMobile>
          {data.sections.length ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {data.sections.map((section) => (
                <div className="rounded-lg border border-gray-800 p-4" key={section.id}>
                  <div className="flex justify-between gap-3"><h3 className="font-medium text-gray-200">{section.title}</h3><Badge variant="outline">{label(section.status)}</Badge></div>
                  <p className="mt-2 text-sm leading-6 text-gray-400">{section.body}</p>
                </div>
              ))}
            </div>
          ) : (
            <Empty action={<EmptyLink href={`/research/${encodeURIComponent(ticker)}?view=documents`}>Añade la primera fuente</EmptyLink>}>
              Sin secciones específicas todavía.
            </Empty>
          )}
        </Panel>
        <Panel title="Afirmaciones y evidencia">
          <MutationForm action={createResearchClaim.bind(null, ticker)} className="mb-5 grid gap-3 sm:grid-cols-[1fr_150px_auto] sm:items-start" resetOnSuccess successMessage="Afirmación creada">
            <Textarea id="statement" name="statement" placeholder="Una afirmación falsable y específica de la empresa" required className="min-h-[44px] text-base sm:text-sm" />
            <Input name="materiality_score" type="number" min="0" max="10" defaultValue="5" className="h-11 text-base sm:h-9 sm:text-sm" />
            <Button type="submit" className="min-h-[44px] sm:min-h-0">Añadir afirmación</Button>
          </MutationForm>
          <div className="space-y-3">
            {data.claims.length ? data.claims.map((claim) => (
              <div className="rounded-lg border border-gray-800 p-4" key={claim.id}>
                <div className="flex flex-wrap gap-2"><Badge variant="outline">{label(claim.status)}</Badge><Badge variant="outline">materialidad {claim.materiality_score}</Badge><Badge variant="outline">{claim.evidence.length} pruebas</Badge></div>
                <p className="mt-3 text-sm text-gray-300">{claim.statement}</p>
              </div>
            )) : (
              <Empty action={<EmptyLink href="#statement">Escribe la primera afirmación</EmptyLink>}>
                Sin afirmaciones registradas.
              </Empty>
            )}
          </div>
        </Panel>
        <Panel title="Grafo de dependencias y red team" collapsibleOnMobile>
          <p className="text-sm text-gray-300">{data.graph ? `${data.graph.nodes.length} nodos · ${data.graph.edges.length} dependencias` : 'Sin grafo persistido.'}</p>
          <p className="mt-2 text-sm text-gray-400">{data.redTeam?.strongest_bear_case ?? 'Sin ejecución de red team persistida.'}</p>
        </Panel>
      </div>
    );
  } else if (activeView === 'changes') {
    const data = await getResearchChangesWorkspace(ticker);
    content = (
      <div className="space-y-6">
        <Panel title="Qué ha cambiado">
          <div className="space-y-3">
            {data.changes.length ? data.changes.map((change) => (
              <div className="rounded-lg border border-gray-800 p-4" key={change.id}>
                <div className="flex flex-wrap gap-2"><Badge>{label(change.impact_direction)}</Badge><Badge variant="outline">{label(change.change_type)}</Badge><Badge variant="outline">materialidad {change.materiality_score}</Badge></div>
                <p className="mt-3 text-sm text-gray-300">{change.summary}</p>
              </div>
            )) : (
              <Empty action={<EmptyLink href="/research/news">Analiza la última noticia</EmptyLink>}>
                Sin cambios materiales registrados.
              </Empty>
            )}
          </div>
        </Panel>
        <div className="grid gap-6 xl:grid-cols-2">
          <Panel title="Revisiones abiertas"><div className="space-y-2">{data.reviews.length ? data.reviews.map((review) => <div className="rounded-lg border border-gray-800 p-3 text-sm text-gray-300" key={review.id}>{review.title}</div>) : <Empty>Sin revisiones abiertas.</Empty>}</div></Panel>
          <Panel title="Alertas"><div className="space-y-2">{data.alerts.length ? data.alerts.map((alert) => <div className="rounded-lg border border-gray-800 p-3 text-sm" key={alert.id}><Badge variant="outline">{label(alert.severity)}</Badge><p className="mt-2 text-gray-300">{alert.message}</p></div>) : <Empty>Sin alertas.</Empty>}</div></Panel>
        </div>
        <DecisionAndRealityPanel ticker={ticker} decisions={data.decisions} reviews={data.expectations} />
      </div>
    );
  } else if (activeView === 'financials') {
    const data = await getResearchFinancialsWorkspace(ticker);
    content = (
      <div className="space-y-6">
        <div className="flex flex-wrap gap-3">
          <MutationForm action={refreshCompanyFinancials.bind(null, ticker)} successMessage="Financieros actualizados desde fuentes gratuitas (Finnhub/EDGAR/Yahoo)"><Button type="submit" variant="outline">Refrescar financieros</Button></MutationForm>
          <MutationForm action={refreshCompanyFinancialsSEC.bind(null, ticker)} successMessage="Financieros SEC refrescados"><Button type="submit" variant="outline">Refrescar SEC</Button></MutationForm>
          <MutationForm action={refreshCompanyResearchModel.bind(null, ticker)} successMessage="Métricas y modelo de research refrescados"><Button type="submit"><RefreshCcw className="mr-2 h-4 w-4" />Recalcular</Button></MutationForm>
        </div>
        <Panel title="Métricas calculadas trazables"><MetricsGrid metrics={data.calculatedMetrics} ticker={ticker} /></Panel>
        <Panel title="Hechos financieros canónicos"><FactTable facts={data.facts} ticker={ticker} /></Panel>
      </div>
    );
  } else if (activeView === 'model') {
    const model = await getResearchLongTermModel(ticker);
    content = (
      <div className="space-y-5">
        <MutationForm action={refreshCompanyResearchModel.bind(null, ticker)} successMessage="Modelo a largo plazo generado"><Button type="submit"><RefreshCcw className="mr-2 h-4 w-4" />Generar modelo</Button></MutationForm>
        <LongTermModelPanel model={model?.status === 'not_generated' ? null : model} />
      </div>
    );
  } else if (activeView === 'market-opportunity') {
    content = <MarketOpportunityView model={await getResearchLongTermModel(ticker)} ticker={ticker} />;
  } else if (activeView === 'moat') {
    const moat = await getResearchMoatWorkspace(ticker);
    content = (
      <div className="space-y-5">
        <MutationForm action={refreshCompanyResearchModel.bind(null, ticker)} successMessage="Evaluación del foso refrescada"><Button type="submit" variant="outline"><ShieldCheck className="mr-2 h-4 w-4" />Reevaluar evidencia</Button></MutationForm>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {moat?.moats.length ? moat.moats.map((item) => {
            const definition = moatDefinition(item.type);
            return (
              <div className="rounded-xl border border-gray-800 bg-[#101010] p-4" key={item.type}>
                <div className="flex justify-between gap-3"><MoatTerm type={item.type} /><Badge>{item.strength}/100</Badge></div>
                <p className="mt-3 text-sm text-gray-400">{label(item.status)} · {label(item.trend)} · persistencia {item.persistence}</p>
                {definition ? <p className="mt-2 text-xs leading-5 text-gray-500">{definition}</p> : null}
                <p className="mt-2 text-xs text-gray-600">{item.supporting_claim_ids.length} afirmaciones a favor · {item.contradicting_claim_ids.length} en contra</p>
              </div>
            );
          }) : (
            <Empty action={<EmptyLink href={`/research/${encodeURIComponent(ticker)}?view=model`}>Genera el modelo y reevalúa el foso</EmptyLink>}>
              Sin evaluación de foso persistida.
            </Empty>
          )}
        </div>
      </div>
    );
  } else if (activeView === 'peers') {
    const peers = await getResearchPeersWorkspace(ticker);
    content = (
      <div className="space-y-6">
        <Panel title="Conjunto de comparables"><p className="text-sm text-gray-300">{peers.comparison?.basis ?? 'Sin conjunto de comparables'} · {peers.comparison?.peer_count ?? 0} comparables</p><div className="mt-4 flex flex-wrap gap-2">{peers.comparison?.companies.map((peer) => <Badge variant={peer.is_target ? 'default' : 'outline'} key={peer.ticker}>{peer.ticker}</Badge>)}</div></Panel>
        <Panel title="Métricas comparables"><div className="grid gap-3 sm:grid-cols-2">{Object.entries(peers.comparison?.benchmarks ?? {}).map(([metric, value]) => <div className="rounded-lg border border-gray-800 p-3" key={metric}><div className="text-sm text-gray-200">{metric}</div><div className="mt-2 text-xs text-gray-500">Objetivo {value.target_value ?? 'desconocido'} · mediana {value.peer_median ?? 'desconocida'} · n={value.peer_sample_size}</div></div>)}</div></Panel>
        <Panel title="Ventajas y desventajas"><p className="text-sm text-gray-400">{peers.analysis?.methodology ?? 'Sin análisis de comparables persistido.'}</p><p className="mt-3 text-xs text-amber-300">{peers.analysis?.insufficient_data.join(', ')}</p></Panel>
      </div>
    );
  } else if (activeView === 'valuation') {
    content = <ValuationView valuation={await getResearchValuationWorkspace(ticker)} currency={company.currency} ticker={ticker} />;
  } else if (activeView === 'documents') {
    const documents = await getResearchDocumentsWorkspace(ticker, false);
    content = (
      <div className="space-y-6">
        <div className="grid gap-6 xl:grid-cols-2">
          <Panel title="Sube una fuente primaria"><MutationForm action={importResearchDocumentFile} className="grid gap-3" successMessage="Documento subido"><input type="hidden" name="ticker" value={ticker} /><Input name="title" placeholder="Título del documento" required /><FileUploadInput name="file" required /><Button type="submit">Subir</Button></MutationForm></Panel>
          <Panel title="Importar desde una URL"><MutationForm action={importResearchDocumentUrl} className="grid gap-3" successMessage="Documento importado"><input type="hidden" name="ticker" value={ticker} /><Input name="title" placeholder="Título del documento" required /><Input name="url" type="url" placeholder="https://..." required /><Input name="source_type" placeholder="sec_filing / investor_relations" defaultValue="url" /><Button type="submit">Importar</Button></MutationForm></Panel>
        </div>
        <Panel title="Documentos">
          {documents.length ? (
            <div className="space-y-3">{documents.map((document) => <div className="rounded-lg border border-gray-800 p-4" key={document.id}><div className="flex flex-wrap items-center gap-2"><FileText className="h-4 w-4 text-teal-300" /><span className="font-medium text-gray-200">{document.title}</span><Badge variant="outline">{label(document.source_tier)}</Badge></div><p className="mt-2 text-xs text-gray-500">{label(document.source_type)} · {document.published_at ? formatDate(document.published_at) : 'fecha desconocida'}</p></div>)}</div>
          ) : (
            <Empty action={<EmptyLink href="/research/sources">Importa tu primer documento</EmptyLink>}>
              Sin documentos ingeridos.
            </Empty>
          )}
        </Panel>
      </div>
    );
  } else if (activeView === 'sources') {
    const audits = await getResearchSourceAuditsWorkspace(ticker);
    content = (
      <Panel title="Auditorías de fuentes">
        {audits.length ? (
          <div className="space-y-3">{audits.slice(0, 100).map((audit) => <div className="rounded-lg border border-gray-800 p-4" key={audit.id}><div className="flex flex-wrap gap-2"><Badge>{audit.passed ? 'superada' : 'fallida'}</Badge><Badge variant="outline">cobertura {audit.source_coverage_score}/100</Badge><Badge variant="outline">tesis {audit.thesis_version_id ?? 'desconocida'}</Badge></div>{audit.required_fixes.length ? <p className="mt-3 text-sm text-amber-300">{audit.required_fixes.join(' · ')}</p> : null}</div>)}</div>
        ) : (
          <Empty action={<EmptyLink href={`/research/${encodeURIComponent(ticker)}?view=thesis`}>Genera una tesis para auditar fuentes</EmptyLink>}>
            Sin auditorías de fuentes persistidas.
          </Empty>
        )}
      </Panel>
    );
  } else {
    const response = query.chat ? await askResearchCompanyChat(ticker, query.chat) : null;
    content = (
      <div className="space-y-6">
        <Panel title="Chat de la empresa con fuentes">
          <form className="flex flex-col gap-3 sm:flex-row" method="get"><input type="hidden" name="view" value="chat" /><Input name="chat" defaultValue={query.chat} placeholder={`Pregunta sobre ${ticker} citando fuentes`} minLength={3} required className="h-11 text-base sm:h-9 sm:text-sm" /><Button type="submit" className="min-h-[44px] sm:min-h-0"><Search className="mr-2 h-4 w-4" />Preguntar</Button></form>
        </Panel>
        {response ? (
          <Panel title="Respuesta">
            <div className="whitespace-pre-wrap text-sm leading-7 text-gray-300">{response.answer}</div>
            <div className="mt-4 flex flex-wrap gap-2"><Badge variant="outline">modelo {response.model ?? 'determinista'}</Badge><Badge variant="outline">{response.sources.length} fuentes</Badge><Badge variant="outline">{response.blocked ? 'datos insuficientes' : 'con evidencia'}</Badge></div>
            <CitationsList citations={[]} sources={response.sources} />
          </Panel>
        ) : (
          <Empty>Haz una pregunta para recuperar el contrato de evidencia determinista y la síntesis con fuentes.</Empty>
        )}
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-[#080808] px-4 py-6 text-gray-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1600px]">
        <Link className="mb-5 inline-flex items-center text-sm text-gray-500 hover:text-gray-200" href="/research"><ArrowLeft className="mr-2 h-4 w-4" />Research</Link>
        <header className="mb-6 flex flex-col gap-4 border-b border-gray-800 pb-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 sm:gap-3"><h1 className="text-2xl font-bold sm:text-3xl">{ticker}</h1><Badge variant="outline">{company.exchange}</Badge><Badge variant="outline">{company.currency}</Badge></div>
            <p className="mt-2 text-sm text-gray-400 sm:text-base">{company.name} · {company.sector} · {company.industry}</p>
          </div>
          <div className="flex flex-col gap-3 border-t border-gray-900 pt-4">
            <div className="flex flex-wrap gap-2 text-xs text-gray-500"><span className="inline-flex items-center gap-1"><Database className="h-4 w-4" />snapshot de solo lectura</span><span className="inline-flex items-center gap-1"><Target className="h-4 w-4" />{label(company.company_type)}</span></div>
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
              <div className="w-full sm:w-auto sm:min-w-0 sm:flex-1"><QuickAlertButton ticker={ticker} /></div>
              <FollowButton symbol={ticker} company={company.name} isFollowed={isFollowed} />
            </div>
          </div>
        </header>
        <nav aria-label="Módulos de research" className="-mx-4 mb-7 flex gap-2 overflow-x-auto px-4 pb-2 [scrollbar-width:thin] sm:mx-0 sm:px-0">
          {views.map(([key, viewLabel]) => (
            <Link className={`inline-flex min-h-[44px] items-center whitespace-nowrap rounded-lg border px-4 py-2.5 text-sm transition sm:min-h-0 sm:px-3 sm:py-2 ${activeView === key ? 'border-teal-600 bg-teal-950/40 text-teal-200' : 'border-gray-800 text-gray-400 hover:border-gray-700 hover:text-gray-200'}`} href={`/research/${encodeURIComponent(ticker)}?view=${key}`} key={key}>{viewLabel}</Link>
          ))}
          {[
            ['financial-terminal', 'Terminal financiero'],
            ['driver-assumptions', 'Supuestos'],
            ['decision-lessons', 'Lecciones'],
            ['management-credibility', 'Directiva'],
          ].map(([path, moduleLabel]) => (
            <Link className="inline-flex min-h-[44px] items-center whitespace-nowrap rounded-lg border border-teal-900/60 px-4 py-2.5 text-sm text-teal-300 transition hover:border-teal-700 hover:text-teal-200 sm:min-h-0 sm:px-3 sm:py-2" href={`/research/${encodeURIComponent(ticker)}/${path}`} key={path}>{moduleLabel}</Link>
          ))}
        </nav>
        {content}
      </div>
    </main>
  );
}

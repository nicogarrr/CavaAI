import { AlertTriangle, ArrowLeft, Minus, TrendingDown, TrendingUp } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { EmptyLink, EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { PageHeader } from '@/components/ui/page-header';
import { Stat } from '@/components/ui/stat';
import { Textarea } from '@/components/ui/textarea';
import { MutationForm } from '@/components/forms/MutationForm';
import { analyzeManualNews, getResearchNews, ingestResearchNewsFeed } from '@/lib/actions/research.actions';
import { getTickerContext } from '@/lib/actions/ticker-context.actions';
import { TickerContextBadges } from '@/components/common/TickerContextBadges';
import { formatPercent, NA } from '@/lib/format';
import { etiquetaTemaMacro, etiquetaTierFuente, etiquetaTipoEvento } from "@/lib/labels";

export const dynamic = 'force-dynamic';
export const revalidate = 0;

async function submitAnalyzeNews(formData: FormData): Promise<void> {
  'use server';
  await analyzeManualNews(formData);
}

async function submitIngestFeed(formData: FormData): Promise<void> {
  'use server';
  await ingestResearchNewsFeed(formData);
}

function pct(value: number | null | undefined) {
  return formatPercent(value ?? null, { digits: 1 }, NA);
}

/** El icono de impacto es el único dato de la celda: se oculta y se deja el
 *  nombre en texto para que un lector de pantalla no lea un glifo suelto. */
const IMPACT_LABELS: Record<string, string> = {
  up: 'alcista',
  positive: 'alcista',
  down: 'bajista',
  negative: 'bajista',
  neutral: 'neutro',
};

type PageProps = { searchParams: Promise<{ lane?: string }> };

const CARRILES = [
  { key: null, label: 'Todas', href: '/research/news' },
  { key: 'empresa', label: 'Empresas', href: '/research/news?lane=empresa' },
  { key: 'macro', label: 'Macro', href: '/research/news?lane=macro' },
] as const;

export default async function ResearchNewsPage({ searchParams }: PageProps) {
  const query = await searchParams;
  const lane = query.lane === 'macro' || query.lane === 'empresa' ? query.lane : null;
  const [events, tickerContext] = await Promise.all([getResearchNews(), getTickerContext()]);
  const portfolioTickers = new Set(tickerContext.portfolioTickers);
  const watchlistTickers = new Set(tickerContext.watchlistTickers);
  // Filtro sobre la ventana que sirve la API (ultimos 100 eventos).
  // 'empresa' = atribuida a una empresa real (ticker presente); un evento
  // sin ticker que tampoco es macro solo aparece en 'Todas'.
  const filtered = lane === 'macro'
    ? events.filter((event) => event.news_lane === 'macro')
    : lane === 'empresa'
      ? events.filter((event) => event.ticker !== null)
      : events;
  const requireUpdate = events.filter((e) => e.requires_update).length;
  const highMateriality = events.filter((e) => e.materiality_score >= 7).length;

  return (
    <main id="content" tabIndex={-1} className="mx-auto flex max-w-7xl flex-col gap-6">
      <PageHeader
        actions={
          <div className="rounded-lg border border-gray-800 bg-surface-1 px-4 py-3 text-sm text-gray-300">
            {events.length} eventos
          </div>
        }
        back={
          <Button asChild size="sm" variant="ghost">
            <Link href="/research">
              <ArrowLeft aria-hidden="true" className="h-4 w-4" />
              Research
            </Link>
          </Button>
        }
        description="Eventos de noticias clasificados por materialidad. Los de empresa muestran impacto sobre posiciones de cartera; el carril macro GDELT no tiene vínculo directo con posiciones."
        kicker="Inteligencia de mercado"
        title="Eventos de noticias"
      />

      <section className="grid gap-4 md:grid-cols-3">
        <Stat label="Eventos totales" value={String(events.length)} />
        <Stat label="Requieren actualización" value={String(requireUpdate)} tone={requireUpdate > 0 ? 'bad' : 'good'} />
        <Stat label="Alta materialidad" value={String(highMateriality)} tone={highMateriality > 0 ? 'warn' : 'good'} />
      </section>

      <section className="rounded-lg border border-gray-800 bg-surface-1 p-5">
        <div className="mb-4 flex items-center gap-2">
          <AlertTriangle aria-hidden="true" className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Flujo de eventos</h2>
        </div>
        <nav aria-label="Filtrar por carril" className="mb-4 flex flex-wrap items-center gap-2 text-xs">
          {CARRILES.map((option) => {
            const active = lane === option.key;
            return (
              <Link
                aria-current={active ? 'page' : undefined}
                className={`rounded-full border px-3 py-1 ${
                  active
                    ? 'border-teal-500 bg-teal-950/60 font-semibold text-teal-300'
                    : 'border-gray-800 text-gray-400 hover:text-gray-200'
                }`}
                href={option.href}
                key={option.label}
              >
                {option.label}
              </Link>
            );
          })}
          <span className="text-gray-500">
            Mostrando {filtered.length} de {events.length}
          </span>
        </nav>
        {/* F176: sin contain, Chrome propaga el overflow horizontal de la
            tabla al documento entero (zoom-out y recorte en movil) aunque la
            region ya scrolla por dentro; layout+paint lo contiene aqui. */}
        <div aria-label="Flujo de eventos de noticias" className="scroll-affordance-x overflow-x-auto [contain:layout_paint]" role="region" tabIndex={0}>
          <table className="w-full min-w-[1080px] text-left text-sm">
            <caption className="sr-only">Eventos de noticias clasificados por materialidad, con impacto sobre la cartera y si exigen actualización</caption>
            <thead className="text-xs uppercase text-gray-500">
              <tr>
                <th className="border-b border-gray-800 py-2" scope="col">Ticker</th>
                <th className="border-b border-gray-800 py-2" scope="col">Fecha</th>
                <th className="border-b border-gray-800 py-2" scope="col">Titular</th>
                <th className="border-b border-gray-800 py-2" scope="col">Fuente</th>
                <th className="border-b border-gray-800 py-2" scope="col">Tipo</th>
                <th className="border-b border-gray-800 py-2 text-right" scope="col">Peso al evaluar</th>
                <th className="border-b border-gray-800 py-2 text-center" scope="col">Materialidad</th>
                <th className="border-b border-gray-800 py-2 text-center" scope="col">Impacto</th>
                <th className="border-b border-gray-800 py-2 text-center" scope="col">¿Actualizar?</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((event) => {
                const materialityColor =
                  event.materiality_score >= 7
                    ? 'text-red-400'
                    : event.materiality_score >= 4
                      ? 'text-amber-400'
                      : 'text-gray-500';

                const dir = event.impact_direction.toLowerCase();
                const DirectionIcon =
                  dir === 'up' || dir === 'positive'
                    ? TrendingUp
                    : dir === 'down' || dir === 'negative'
                      ? TrendingDown
                      : Minus;

                return (
                  <tr key={event.id} className="border-b border-gray-900 last:border-0">
                    <th className="py-3 text-left text-sm font-semibold" scope="row">
                      {event.ticker ? (
                        <Link
                          className="text-teal-300 hover:text-teal-200"
                          href={`/research/${event.ticker}`}
                        >
                          {event.ticker}
                        </Link>
                      ) : (
                        <span className="text-gray-500">—</span>
                      )}
                      {event.ticker ? (
                        <TickerContextBadges
                          portfolioTickers={portfolioTickers}
                          ticker={event.ticker}
                          watchlistTickers={watchlistTickers}
                        />
                      ) : null}
                      {event.news_lane === 'macro' ? (
                        <div className="mt-1">
                          <span className="rounded-full bg-indigo-950/60 px-2 py-0.5 text-xs font-semibold text-indigo-300">
                            macro{event.macro_theme ? ` · ${etiquetaTemaMacro(event.macro_theme)}` : ''}
                          </span>
                        </div>
                      ) : null}
                    </th>
                    <td className="py-3 text-gray-400">
                      <div>{event.date.split('T')[0]}</div>
                      {event.date_source === 'ingested_at_fallback' ? (
                        <div className="mt-1 text-xs text-gray-500">fecha de ingesta · la fuente no da fecha</div>
                      ) : null}
                      {event.date_source === 'gdelt_first_seen' ? (
                        <div className="mt-1 text-xs text-gray-500">primera detección de GDELT · no es la fecha de publicación</div>
                      ) : null}
                    </td>
                    <td className="max-w-[360px] py-3 text-gray-300">
                      <div className="truncate">
                        {event.url ? (
                          <a className="hover:text-teal-200" href={event.url} rel="noreferrer" target="_blank">
                            {event.title}
                          </a>
                        ) : (
                          event.title
                        )}
                      </div>
                    </td>
                    <td className="py-3 text-gray-400">
                      <div>{event.source}</div>
                      <div className="mt-1 text-xs text-gray-500">{event.source_tier ? etiquetaTierFuente(event.source_tier) : 'tier desconocido'}</div>
                    </td>
                    <td className="py-3 text-gray-400">{etiquetaTipoEvento(event.event_type)}</td>
                    <td className="py-3 text-right text-gray-400">{pct(event.portfolio_weight)}</td>
                    <td className="py-3 text-center">
                      <span className={`font-semibold ${materialityColor}`}>
                        {event.materiality_score}
                      </span>
                    </td>
                    <td className="py-3 text-center">
                      <DirectionIcon aria-hidden="true" className="inline-block h-4 w-4 text-gray-400" />
                      <span className="sr-only">{IMPACT_LABELS[dir] ?? dir}</span>
                    </td>
                    <td className="py-3 text-center">
                      {event.requires_update ? (
                        <span className="rounded-full bg-red-950/60 px-2 py-0.5 text-xs font-semibold text-red-400">
                          urgente
                        </span>
                      ) : (
                        <span className="rounded-full bg-gray-900 px-2 py-0.5 text-xs text-gray-500">
                          ok
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {!events.length ? (
                <tr>
                  <td className="p-0" colSpan={9}>
                    <EmptyState
                      action={<EmptyLink href="/research/sources">Importa una fuente o analiza una noticia manual</EmptyLink>}
                      className="rounded-none border-0 p-6"
                      title="Sin eventos de noticias todavía."
                    />
                  </td>
                </tr>
              ) : null}
              {events.length > 0 && !filtered.length ? (
                <tr>
                  <td className="p-6 text-center text-sm text-gray-500" colSpan={9}>
                    Sin eventos en este carril dentro de los últimos {events.length} cargados.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border border-gray-800 bg-surface-1 p-5">
        <div className="mb-4 flex items-center gap-2">
          <AlertTriangle aria-hidden="true" className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Analizar noticia manual</h2>
        </div>
        <MutationForm action={submitAnalyzeNews} className="grid gap-3" resetOnSuccess successMessage="Noticia analizada">
          <div className="grid gap-2">
            <label className="text-sm font-semibold text-gray-400" htmlFor="text">
              Texto de la noticia
            </label>
            <Textarea
              className="min-h-[160px] border-gray-800 bg-black/30 text-gray-200 focus-visible:ring-teal-500"
              id="text"
              name="text"
              placeholder="Pega aquí el artículo, la nota de prensa o la nota de relaciones con inversores..."
              required
            />
          </div>
          <div className="grid gap-2 sm:grid-cols-[160px_1fr] sm:items-center">
            <label className="text-sm font-semibold text-gray-400" htmlFor="source">
              Fuente
            </label>
            <Input id="source" name="source" placeholder="Bloomberg, FT, RI..." />
          </div>
          <div className="grid gap-2 sm:grid-cols-[160px_1fr] sm:items-center">
            <label className="text-sm font-semibold text-gray-400" htmlFor="url">
              URL de la fuente
            </label>
            <Input id="url" name="url" placeholder="https://..." type="url" />
          </div>
          <Button className="w-full sm:w-fit" type="submit">
            Analizar noticia
          </Button>
        </MutationForm>
      </section>

      <section className="rounded-lg border border-gray-800 bg-surface-1 p-5">
        <div className="mb-4 flex items-center gap-2">
          <AlertTriangle aria-hidden="true" className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Ingerir lote de feed</h2>
        </div>
        <MutationForm action={submitIngestFeed} className="grid gap-3" resetOnSuccess successMessage="Feed importado">
          <div className="grid gap-2 sm:grid-cols-[160px_1fr] sm:items-center">
            <label className="text-sm font-semibold text-gray-400" htmlFor="feed-source">
              Fuente
            </label>
            <Input defaultValue="manual_feed" id="feed-source" name="source" />
          </div>
          <Textarea
            className="min-h-[180px] border-gray-800 bg-black/30 font-mono text-xs text-gray-200 focus-visible:ring-teal-500"
            name="items"
            placeholder='[{"ticker":"MSFT","title":"MSFT recorta guía","text":"resultado por debajo y recorte de guía","url":"https://..."}]'
            required
          />
          <Button className="w-full sm:w-fit" type="submit" variant="outline">
            Ingerir feed
          </Button>
        </MutationForm>
      </section>
    </main>
  );
}

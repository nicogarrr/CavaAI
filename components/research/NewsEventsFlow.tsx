"use client";

import { AlertTriangle } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { EmptyLink, EmptyState } from '@/components/ui/empty-state';
import { TickerContextBadges } from '@/components/common/TickerContextBadges';
import { loadMoreResearchNews, type ResearchNewsEvent } from '@/lib/actions/research.actions';
import { NEWS_PAGE_SIZE, type NewsLane } from '@/lib/news-paging';
import { formatPercent, NA } from '@/lib/format';
import { newsDisplayTitle } from '@/lib/news-display';
import { etiquetaDireccionImpacto, etiquetaTemaMacro, etiquetaTierFuente, etiquetaTipoEvento } from "@/lib/labels";

const CARRILES = [
  { key: null, label: 'Todas', href: '/research/news' },
  { key: 'empresa', label: 'Empresas', href: '/research/news?lane=empresa' },
  { key: 'macro', label: 'Macro', href: '/research/news?lane=macro' },
] as const;

/**
 * Flujo de eventos con scroll infinito: la primera página llega del servidor
 * y el resto se pide por páginas de NEWS_PAGE_SIZE al acercarse al final. El
 * carril se filtra en la API (no sobre una ventana fija), así que "Macro" y
 * "Empresas" recorren todo el histórico.
 */
export function NewsEventsFlow({
  initialEvents,
  lane,
  portfolioTickers,
  watchlistTickers,
}: {
  initialEvents: ResearchNewsEvent[];
  lane: NewsLane;
  portfolioTickers: string[];
  watchlistTickers: string[];
}) {
  const portfolioSet = useMemo(() => new Set(portfolioTickers), [portfolioTickers]);
  const watchlistSet = useMemo(() => new Set(watchlistTickers), [watchlistTickers]);
  const [events, setEvents] = useState<ResearchNewsEvent[]>(initialEvents);
  const [hasMore, setHasMore] = useState(initialEvents.length >= NEWS_PAGE_SIZE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const busy = useRef(false);

  const loadMore = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    setLoading(true);
    setError(false);
    try {
      const next = await loadMoreResearchNews(lane, events.length, NEWS_PAGE_SIZE);
      const known = new Set(events.map((event) => event.id));
      const fresh = next.filter((event) => !known.has(event.id));
      setEvents((current) => [...current, ...fresh]);
      setHasMore(next.length >= NEWS_PAGE_SIZE && fresh.length > 0);
    } catch {
      setError(true);
    } finally {
      busy.current = false;
      setLoading(false);
    }
  }, [events, lane]);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || !hasMore || error || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void loadMore();
      },
      { rootMargin: '400px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, error, loadMore]);

  return (
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
            {events.length} {events.length === 1 ? 'evento cargado' : 'eventos cargados'}
          </span>
        </nav>
        {/* F176: sin contain, Chrome propaga el overflow horizontal de la
            tabla al documento entero (zoom-out y recorte en movil) aunque la
            region ya scrolla por dentro; layout+paint lo contiene aqui. */}
        {/* Movil: una tarjeta por noticia (titular completo, fecha, fuente). La
            tabla de 5 columnas solo se usa desde md; en pantallas estrechas
            cortaba titulares y partia el layout. */}
        <ul aria-label="Eventos de noticias" className="flex flex-col gap-3 md:hidden">
          {events.map((event) => {
            const materialityColor =
              event.materiality_score >= 7
                ? 'text-red-400'
                : event.materiality_score >= 4
                  ? 'text-amber-400'
                  : 'text-gray-500';
            const title = newsDisplayTitle(event.title, event.ticker, event.headline_from_source);
            return (
              <li className="rounded-lg border border-gray-800 bg-black/20 p-3" key={`card-${event.id}`}>
                <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
                  {event.ticker ? (
                    <Link className="font-semibold text-teal-300 hover:text-teal-200" href={`/research/${event.ticker}`}>
                      {event.ticker}
                    </Link>
                  ) : null}
                  {event.news_lane === 'macro' ? (
                    <span className="rounded-full bg-indigo-950/60 px-2 py-0.5 font-semibold text-indigo-300">
                      macro{event.macro_theme ? ` · ${etiquetaTemaMacro(event.macro_theme)}` : ''}
                    </span>
                  ) : null}
                  <span>{event.date.split('T')[0]}</span>
                  {event.date_source === 'gdelt_first_seen' ? (
                    <span className="rounded-full bg-gray-900 px-2 py-0.5 text-gray-400" title="Fecha de primera detección en GDELT, no de publicación">vía GDELT</span>
                  ) : null}
                  {event.date_source === 'ingested_at_fallback' ? (
                    <span className="rounded-full bg-gray-900 px-2 py-0.5 text-gray-400">fecha de ingesta</span>
                  ) : null}
                  <span className={`ml-auto font-semibold ${materialityColor}`}>{event.materiality_score}</span>
                </div>
                <p className="mt-2 break-words text-sm text-gray-200">
                  {event.url ? (
                    <a className="hover:text-teal-200" href={event.url} rel="noreferrer" target="_blank">
                      {title}
                    </a>
                  ) : (
                    title
                  )}
                </p>
                <div className="mt-2 flex items-center justify-between gap-2 text-xs text-gray-500">
                  <span className="min-w-0 break-words">{event.source || NA}</span>
                  {event.requires_update ? (
                    <span className="shrink-0 rounded-full bg-amber-950/60 px-2 py-0.5 text-amber-300">Revisar</span>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
        <div aria-label="Flujo de eventos de noticias" className="scroll-affordance-x overflow-x-auto [contain:layout_paint] hidden md:block" role="region" tabIndex={0}>
          <table className="w-full min-w-[650px] text-left text-sm">
            <caption className="sr-only">Eventos de noticias con materialidad y detalles de la fuente por fila</caption>
            <thead className="text-xs uppercase text-gray-500">
              <tr>
                <th className="border-b border-gray-800 py-2" scope="col">Ticker</th>
                <th className="border-b border-gray-800 py-2" scope="col">Fecha</th>
                <th className="border-b border-gray-800 py-2" scope="col">Titular</th>
                <th className="border-b border-gray-800 py-2 text-center" scope="col">Materialidad</th>
                <th className="border-b border-gray-800 py-2" scope="col">Estado y detalle</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => {
                const materialityColor =
                  event.materiality_score >= 7
                    ? 'text-red-400'
                    : event.materiality_score >= 4
                      ? 'text-amber-400'
                      : 'text-gray-500';

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
                          portfolioTickers={portfolioSet}
                          ticker={event.ticker}
                          watchlistTickers={watchlistSet}
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
                        <div className="mt-1 text-xs text-gray-500" title="Fecha de primera detección en GDELT, no de publicación">vía GDELT</div>
                      ) : null}
                    </td>
                    <td className="max-w-[360px] py-3 text-gray-300">
                      <div className="break-words">
                        {event.url ? (
                          <a className="hover:text-teal-200" href={event.url} rel="noreferrer" target="_blank">
                            {newsDisplayTitle(event.title, event.ticker, event.headline_from_source)}
                          </a>
                        ) : (
                          newsDisplayTitle(event.title, event.ticker, event.headline_from_source)
                        )}
                      </div>
                    </td>
                    <td className="py-3 text-center">
                      <span className={`font-semibold ${materialityColor}`}>{event.materiality_score}</span>
                    </td>
                    <td className="py-3 text-gray-300">
                      {event.requires_update ? <span className="rounded-full bg-amber-950/60 px-2 py-0.5 text-xs text-amber-300">Revisar</span> : <span className="rounded-full bg-gray-900 px-2 py-0.5 text-xs text-gray-400">Sin revisión pendiente</span>}
                      <details className="mt-2 max-w-xs text-xs text-gray-400">
                        <summary className="min-h-10 cursor-pointer py-2 text-teal-300">Ver contexto</summary>
                        <dl className="mt-1 space-y-1 break-words rounded-md border border-gray-800 p-2">
                          <div><dt className="inline font-medium">Fuente: </dt><dd className="inline">{event.source || NA}</dd></div>
                          <div><dt className="inline font-medium">Tipo: </dt><dd className="inline">{etiquetaTipoEvento(event.event_type)}</dd></div>
                          {/* Datos decisionales reubicados (SERIE 1, auditoria): nunca crudos, nulos etiquetados "sin datos". */}
                          <div><dt className="inline font-medium">Tier de fuente: </dt><dd className="inline">{event.source_tier ? etiquetaTierFuente(event.source_tier) : NA}</dd></div>
                          <div><dt className="inline font-medium">Impacto: </dt><dd className="inline">{event.impact_direction ? etiquetaDireccionImpacto(event.impact_direction) : NA}</dd></div>
                          <div><dt className="inline font-medium">Peso en cartera: </dt><dd className="inline">{event.portfolio_weight != null ? formatPercent(event.portfolio_weight, { digits: 1 }) : NA}</dd></div>
                          {event.news_lane === 'macro' && event.macro_theme ? <div><dt className="inline font-medium">Tema: </dt><dd className="inline">{etiquetaTemaMacro(event.macro_theme)}</dd></div> : null}
                        </dl>
                      </details>
                    </td>
                  </tr>
                );
              })}
              {!events.length && !loading ? (
                <tr>
                  <td className="p-0" colSpan={5}>
                    <EmptyState
                      action={<EmptyLink href="/research/sources">Importa una fuente o analiza una noticia manual</EmptyLink>}
                      className="rounded-none border-0 p-6"
                      title="Sin eventos de noticias todavía."
                    />
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="mt-4 flex flex-col items-center gap-2" ref={sentinelRef}>
          {loading ? <p className="text-xs text-gray-500" role="status">Cargando más eventos…</p> : null}
          {error ? (
            <p className="text-xs text-red-400" role="alert">
              No se pudieron cargar más eventos.{' '}
              <button className="underline" onClick={() => void loadMore()} type="button">Reintentar</button>
            </p>
          ) : null}
          {!loading && !error && hasMore ? (
            <Button onClick={() => void loadMore()} size="sm" type="button" variant="outline">Cargar más</Button>
          ) : null}
          {!hasMore && events.length > 0 ? (
            <p className="text-xs text-gray-500">No hay más eventos.</p>
          ) : null}
        </div>
      </section>
  );
}

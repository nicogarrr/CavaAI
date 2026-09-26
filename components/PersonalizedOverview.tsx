'use client';

import { formatCompact, formatDateTime, formatMoney, formatNumber, formatPercent, NA } from '@/lib/format';
import { memo, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Activity, ArrowRight, BellRing, Eye, Gem, TrendingDown, TrendingUp, Wallet } from 'lucide-react';
import { getPortfolioSummary, type PortfolioHolding, type PortfolioSummary } from '@/lib/actions/portfolio.actions';
import { getWatchlist } from '@/lib/actions/watchlist.actions';
import { getMarketIndices } from '@/lib/actions/market.actions';
import { sectionError } from '@/lib/section-error';
import { getStockFinancialData, getStockQuote } from '@/lib/actions/finnhub.actions';
import { getScreenerStocksReal, getFairValue } from '@/lib/actions/screener.actions';
import {
    getRecentTriggeredAlerts,
    getUserAlerts,
    type Alert,
    type TriggeredAlertDelivery,
} from '@/lib/actions/alerts.actions';
import { t } from '@/lib/i18n/t';

interface PersonalizedOverviewProps {
    userId: string;
}

interface WatchlistItem {
    symbol: string;
    name: string;
    price: number;
    changePercent: number;
}

interface MarketIndex {
    symbol: string;
    name: string;
    price: number;
    change: number;
    changePercent: number;
}

interface UndervaluedStock {
    symbol: string;
    name: string;
    price: number;
    fairValue: number;
    upside: number;
}

/** El universo de candidatos es todo el que devuelve /api/screeners/real por
 *  encima de este market cap. Antes se filtraba por `sector: 'Technology'`
 *  (duplicaba /screener?sector=Technology sin decirlo); ahora el filtro es el
 *  tamaño y la tarjeta lo dice. */
const MIN_MARKET_CAP = 10_000_000_000;

// Tarjeta memorizada: la parrilla de índices re-renderiza con cada
// actualización del dashboard; memo evita reconciliar tarjetas sin cambios.
const MarketIndexCard = memo(function MarketIndexCard({ index }: { index: MarketIndex }) {
    return (
        <Card className="bg-gray-800/40 border-gray-700/50 hover:bg-gray-800/60 transition-colors">
            <CardContent className="p-4 flex items-center justify-between gap-3">
                <div className="min-w-0">
                    <p className="text-sm text-gray-400 font-medium truncate">{index.name}</p>
                    <p className="text-xl font-bold text-white mt-1">{formatMoney(index.price)}</p>
                </div>
                <div className={`shrink-0 text-right ${index.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    <div className="flex items-center justify-end gap-1">
                        {index.changePercent >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                        <span className="font-bold">{formatPercent(index.changePercent, { fromRatio: false, digits: 2, signDisplay: 'always' })}</span>
                    </div>
                    <p className="text-xs mt-1">{formatNumber(index.change, { signDisplay: 'always' })}</p>
                </div>
            </CardContent>
        </Card>
    );
});

/**
 * Estado de carga por sección con el patrón de components/LoadingState.tsx: el
 * texto vive en un nodo `sr-only` y el esqueleto va `aria-hidden`. Antes cada
 * sección escribía su propio `role="status"` con `aria-label` (que no se
 * anuncia) y cuatro variantes distintas de `animate-pulse`.
 */
function SectionSkeleton({ rows = 3, className }: { rows?: number; className?: string }) {
    return (
        <div className={className}>
            <span className="sr-only" role="status">Cargando…</span>
            <div aria-hidden="true" className="space-y-3">
                {Array.from({ length: rows }).map((_, index) => (
                    <Skeleton className="h-12 w-full" key={index} />
                ))}
            </div>
        </div>
    );
}



function InlineSectionError({ message, onRetry }: { message: string; onRetry: () => void }) {
    return (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-900/60 bg-amber-950/20 p-3 text-sm text-amber-200" role="status">
            <span>{message}</span>
            <button type="button" onClick={onRetry} className="underline hover:text-amber-100">Reintentar</button>
        </div>
    );
}

/** El backend devuelve la severidad en inglés ("high", "critical"): sin
 *  traducirla se colaba copy en inglés en la UI. */
const SEVERITY_LABELS: Record<string, string> = {
    critical: 'crítica',
    high: 'alta',
    medium: 'media',
    low: 'baja',
    info: 'informativa',
};

/** Una regla de alerta en una línea legible: "AAPL: precio por encima de 200". */
function alertRuleLabel(alert: Alert): string {
    const labels: Record<Alert['type'], string> = {
        price_above: t('alerts.types.priceAbove'),
        price_below: t('alerts.types.priceBelow'),
        price_change: t('alerts.types.priceChange'),
        news: t('alerts.types.news'),
        earnings: t('alerts.types.earnings'),
    };
    if (alert.type === 'news' || alert.type === 'earnings') return `${alert.symbol}: ${labels[alert.type]}`;
    const value = typeof alert.condition.value === 'number'
        ? formatNumber(alert.condition.value, { maximumFractionDigits: 2 })
        : String(alert.condition.value);
    return `${alert.symbol}: ${labels[alert.type]} ${value}`;
}

/** Envuelve una lectura para que un fallo aislado no tumbe la sección: el
 *  resultado llega siempre con su mensaje de error al lado. */
function settle<T>(promise: Promise<T>, fallback: T): Promise<{ data: T; error: string | null }> {
    return promise
        .then((data) => ({ data, error: null as string | null }))
        .catch((error) => ({ data: fallback, error: sectionError(error) }));
}

export default function PersonalizedOverview({ userId }: PersonalizedOverviewProps) {
    const [reloadToken, setReloadToken] = useState(0);
    const [portfolioSummary, setPortfolioSummary] = useState<PortfolioSummary | null>(null);
    const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
    const [alerts, setAlerts] = useState<Alert[]>([]);
    const [triggeredAlerts, setTriggeredAlerts] = useState<TriggeredAlertDelivery[]>([]);
    const [aiInsight, setAiInsight] = useState('');
    const [marketIndices, setMarketIndices] = useState<MarketIndex[]>([]);
    const [opportunities, setOpportunities] = useState<UndervaluedStock[]>([]);
    const [indicesLoading, setIndicesLoading] = useState(true);
    const [portfolioLoading, setPortfolioLoading] = useState(true);
    const [watchlistLoading, setWatchlistLoading] = useState(true);
    const [opportunitiesLoading, setOpportunitiesLoading] = useState(true);
    const [alertsLoading, setAlertsLoading] = useState(true);
    const [indicesError, setIndicesError] = useState<string | null>(null);
    const [portfolioError, setPortfolioError] = useState<string | null>(null);
    const [watchlistError, setWatchlistError] = useState<string | null>(null);
    const [opportunitiesError, setOpportunitiesError] = useState<string | null>(null);
    const [alertsError, setAlertsError] = useState<string | null>(null);

    useEffect(() => {
        let active = true;

        const loadData = async () => {
            setIndicesLoading(true);
            setPortfolioLoading(true);
            setWatchlistLoading(true);
            setOpportunitiesLoading(true);
            setAlertsLoading(true);
            setIndicesError(null);
            setPortfolioError(null);
            setWatchlistError(null);
            setOpportunitiesError(null);
            setAlertsError(null);

            // Las lecturas base no dependen entre sí. Lanzarlas juntas elimina el
            // waterfall de índices, cartera, watchlist, alertas y screener.
            const [indicesResult, summaryResult, watchlistResult, screenerResult, alertsResult] = await Promise.all([
                settle(getMarketIndices(), [] as Awaited<ReturnType<typeof getMarketIndices>>),
                settle(getPortfolioSummary(userId), null as PortfolioSummary | null),
                settle(getWatchlist(), [] as Awaited<ReturnType<typeof getWatchlist>>),
                settle(getScreenerStocksReal({ marketCapMoreThan: MIN_MARKET_CAP, limit: 10 }), [] as Awaited<ReturnType<typeof getScreenerStocksReal>>),
                settle(
                    Promise.all([getUserAlerts(), getRecentTriggeredAlerts(3)]).then(([rules, triggered]) => ({ rules, triggered })),
                    { rules: [] as Alert[], triggered: [] as TriggeredAlertDelivery[] },
                ),
            ]);
            if (!active) return;

            setMarketIndices(indicesResult.data
                .map((data) => ({
                    symbol: data.symbol,
                    name: data.name,
                    price: data.price || 0,
                    change: data.change || 0,
                    changePercent: data.changePercent || 0,
                }))
                .filter((i) => i.price > 0));
            setIndicesLoading(false);
            setIndicesError(indicesResult.error);

            setPortfolioSummary(summaryResult.data);
            setPortfolioLoading(false);
            setPortfolioError(summaryResult.error);

            setAlerts(alertsResult.data.rules);
            setTriggeredAlerts(alertsResult.data.triggered);
            setAlertsLoading(false);
            setAlertsError(alertsResult.error);

            // Los candidatos sólo dependen del screener; sus cálculos de DCF y
            // quote sí se lanzan en paralelo por símbolo.
            const candidates = (screenerResult.data?.map((s) => s.symbol) ?? []).slice(0, 6);
            const opportunitiesPromise = Promise.all(candidates.map(async (sym: string) => {
                try {
                    const [fairValue, quote] = await Promise.all([getFairValue(sym), getStockQuote(sym)]);
                    const currentPrice = quote?.c || 0;
                    if (fairValue && currentPrice > 0) {
                        const upside = ((fairValue - currentPrice) / currentPrice) * 100;
                        return upside > 5
                            ? { symbol: sym, name: sym, price: currentPrice, fairValue, upside }
                            : null;
                    }
                    return null;
                } catch {
                    return null;
                }
            })).then((results) => results.filter((op): op is UndervaluedStock => op !== null).sort((a, b) => b.upside - a.upside).slice(0, 4));

            const watchlistItems = watchlistResult.data;
            const watchlistPromise = Promise.all(watchlistItems.slice(0, 5).map(async (item): Promise<WatchlistItem> => {
                try {
                    const data = await getStockFinancialData(item.symbol);
                    return {
                        symbol: item.symbol,
                        name: data?.profile?.name || item.symbol,
                        price: data?.quote?.c || 0,
                        changePercent: data?.quote?.dp || 0,
                    };
                } catch {
                    return { symbol: item.symbol, name: item.symbol, price: 0, changePercent: 0 };
                }
            }));

            const [opportunitiesResult, watchlistWithPrices] = await Promise.all([
                opportunitiesPromise.then((data) => ({ data, error: null as string | null })).catch((error) => ({ data: [] as UndervaluedStock[], error: sectionError(error) })),
                watchlistPromise.then((data) => ({ data, error: null as string | null })).catch((error) => ({ data: [] as WatchlistItem[], error: sectionError(error) })),
            ]);
            if (!active) return;

            setOpportunities(opportunitiesResult.data);
            setOpportunitiesLoading(false);
            setOpportunitiesError(opportunitiesResult.error ?? screenerResult.error);
            setWatchlist(watchlistWithPrices.data);
            setWatchlistLoading(false);
            setWatchlistError(watchlistWithPrices.error ?? watchlistResult.error);

            if (summaryResult.data && summaryResult.data.holdings.length > 0) {
                const summary = summaryResult.data;
                // F17: gainPercent es rentabilidad desde la compra (no la
                // variacion de hoy) y solo existe con base de coste. Sin
                // coste no hay frase de movimiento: un "0,00%" seria inventado.
                const conCoste = summary.holdings.filter((h) => h.cost > 0 && !h.fxMissing);
                if (conCoste.length === 0) {
                    setAiInsight('Todavía no tenemos la base de coste de tus posiciones. Cuando esté cargada, aquí verás cómo va tu cartera desde la compra.');
                } else {
                    const topMover = conCoste.reduce((a, b) => Math.abs(b.gainPercent) > Math.abs(a.gainPercent) ? b : a);
                    const costeTotal = conCoste.reduce((sum, h) => sum + h.cost, 0);
                    const gananciaTotal = conCoste.reduce((sum, h) => sum + h.gain, 0);
                    const totalPercent = costeTotal > 0 ? (gananciaTotal / costeTotal) * 100 : 0;
                    const direccion = totalPercent >= 0 ? 'una subida' : 'una caída';
                    setAiInsight(`Tu cartera acumula ${direccion} del ${formatPercent(totalPercent, { fromRatio: false, digits: 2, signDisplay: 'never' })} desde la compra. ${topMover.symbol} es la posición que más se mueve (${formatPercent(topMover.gainPercent, { fromRatio: false, digits: 2, signDisplay: 'always' })}).`);
                }
            } else {
                setAiInsight('');
            }
        };

        void loadData();
        return () => {
            active = false;
        };
        // reloadToken es un disparador explícito del botón Reintentar.
    }, [userId, reloadToken]);

    const retry = () => setReloadToken((value) => value + 1);

    // Derivados memorizados: evita reordenar el estado en cada render
    // (.sort() mutaba el array del estado) y recalcula solo si cambian los datos.
    const sortedHoldings = useMemo(() => {
        if (!portfolioSummary) return [];
        return [...portfolioSummary.holdings]
            .sort((a, b) => Math.abs(b.gainPercent) - Math.abs(a.gainPercent))
            .slice(0, 4);
    }, [portfolioSummary]);

    /** Posición que más se mueve desde la compra: el destino del enlace
     *  "¿qué ha cambiado?" del encabezado. Sin base de coste no hay dato. */
    const topMover = useMemo<PortfolioHolding | null>(() => {
        const conCoste = (portfolioSummary?.holdings ?? []).filter((h) => h.cost > 0 && !h.fxMissing);
        if (!conCoste.length) return null;
        return conCoste.reduce((a, b) => Math.abs(b.gainPercent) > Math.abs(a.gainPercent) ? b : a);
    }, [portfolioSummary]);

    return (
        <div className="space-y-6">
            {/* Encabezado: el h1 es el dato accionable del día, no un saludo. */}
            <div>
                <p className="text-sm font-semibold uppercase text-teal-300">Tu research hoy</p>
                <h1 className="mt-1 text-2xl font-bold break-words text-gray-100 sm:text-3xl">Qué ha cambiado</h1>
                <p className="mt-1 text-sm text-gray-400 sm:text-base">
                    Primero lo que ha cambiado en tus posiciones, luego el valor de la cartera, las alertas
                    disparadas y dónde buscar nuevas ideas.
                </p>
            </div>

            {/* 1 · Insight de cartera: qué ha cambiado y dónde leerlo. Si la
                lectura de cartera falla no se muestra: el error y su reintento
                los pone la tarjeta siguiente, que es la dueña del dato. */}
            {!portfolioError && (
            <Card className="border-teal-800/50 bg-teal-950/20">
                <CardContent className="p-4 flex flex-col min-[420px]:flex-row min-[420px]:items-center gap-4">
                    <div className="p-3 bg-teal-500/10 rounded-full shrink-0">
                        <Activity aria-hidden="true" className="h-6 w-6 text-teal-400" />
                    </div>
                    <div className="min-w-0">
                        <h2 className="text-sm font-semibold text-teal-300 mb-1">Tu cartera en una línea</h2>
                        {portfolioLoading ? (
                            <SectionSkeleton className="max-w-md" rows={1} />
                        ) : (
                            <>
                                <p className="text-gray-200 text-sm leading-relaxed">
                                    {aiInsight || 'Todavía no tienes posiciones. Añade tu primera inversión para ver aquí qué ha cambiado desde la compra.'}
                                </p>
                                <Link
                                    href={topMover ? `/research/${topMover.symbol}?view=changes` : '/portfolio'}
                                    className="mt-3 inline-flex min-h-[44px] items-center gap-1 text-sm text-teal-300 hover:text-teal-200"
                                >
                                    <span className="whitespace-nowrap">
                                        {topMover ? `Ver qué ha cambiado en ${topMover.symbol}` : 'Revisar tu cartera'}
                                    </span>
                                    <ArrowRight aria-hidden="true" className="w-4 h-4 shrink-0" />
                                </Link>
                            </>
                        )}
                    </div>
                </CardContent>
            </Card>
            )}

            {/* 2 · Cartera hoy. */}
            <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-gray-700/50">
                    <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                        <Wallet aria-hidden="true" className="h-5 w-5 text-blue-400" />
                        Tu Cartera Hoy
                    </CardTitle>
                    <Link href="/portfolio" className="inline-flex min-h-[44px] items-center gap-1 px-2 -mr-2 text-blue-400 hover:text-blue-300 text-sm transition-colors">
                        <span className="whitespace-nowrap">Ver detalles</span> <ArrowRight aria-hidden="true" className="w-4 h-4 shrink-0" />
                    </Link>
                </CardHeader>
                <CardContent className="pt-4">
                    {portfolioLoading ? (
                        <SectionSkeleton rows={2} />
                    ) : portfolioError ? (
                        <InlineSectionError message={portfolioError} onRetry={retry} />
                    ) : portfolioSummary && portfolioSummary.holdings.length > 0 ? (
                        <div className="space-y-5">
                            <div className="flex flex-col min-[420px]:flex-row min-[420px]:justify-between min-[420px]:items-center gap-3 p-4 bg-gray-900/60 rounded-xl border border-gray-700/50">
                                <div className="min-w-0">
                                    <p className="text-sm text-gray-400">Valor Total Estimado</p>
                                    <p className="text-2xl sm:text-3xl font-bold text-white mt-1 break-words">{formatMoney(portfolioSummary.totalValue)}</p>
                                </div>
                                <div className="text-right">
                                    <p className="text-sm text-gray-400">Ganancia/Pérdida Total</p>
                                    <p className={`text-xl font-bold mt-1 ${portfolioSummary.totalGainPercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                        {formatPercent(portfolioSummary.totalGainPercent, { fromRatio: false, digits: 2, signDisplay: 'always' })}
                                    </p>
                                </div>
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                {sortedHoldings
                                    .map((h) => (
                                        <Link
                                            key={h.symbol}
                                            href={`/research/${h.symbol}`}
                                            prefetch
                                            className="flex min-h-[44px] items-center justify-between gap-2 p-3 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors border border-gray-700/30"
                                        >
                                            <span className="text-white font-semibold">{h.symbol}</span>
                                            <span className={`font-mono ${h.cost > 0 ? (h.gainPercent >= 0 ? 'text-green-400' : 'text-red-400') : 'text-gray-500'}`}>
                                                {h.cost > 0 ? formatPercent(h.gainPercent, { fromRatio: false, digits: 2, signDisplay: 'always' }) : NA}
                                            </span>
                                        </Link>
                                    ))}
                            </div>
                        </div>
                    ) : (
                        <div className="text-center py-10">
                            <div className="w-16 h-16 bg-gray-800 rounded-full flex items-center justify-center mx-auto mb-4">
                                <Wallet aria-hidden="true" className="h-8 w-8 text-gray-500" />
                            </div>
                            <h3 className="text-lg font-medium text-white mb-2">Comienza tu viaje</h3>
                            <p className="text-gray-400 text-sm max-w-xs mx-auto mb-6">Añade tu primera inversión para ver análisis y métricas detalladas.</p>
                            <Link href="/portfolio" className="inline-flex min-h-[44px] items-center justify-center bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-full transition-colors font-medium">
                                Añadir inversión
                            </Link>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* 3 · Alertas: la sección que faltaba en el inicio pese a existir /alerts. */}
            <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-gray-700/50">
                    <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                        <BellRing aria-hidden="true" className="h-5 w-5 text-amber-400" />
                        Alertas
                    </CardTitle>
                    <Link href="/alerts" className="inline-flex min-h-[44px] items-center gap-1 px-2 -mr-2 text-amber-400 hover:text-amber-300 text-sm transition-colors">
                        <span className="whitespace-nowrap">Gestionar</span> <ArrowRight aria-hidden="true" className="w-4 h-4 shrink-0" />
                    </Link>
                </CardHeader>
                <CardContent className="pt-4">
                    {alertsLoading ? (
                        <SectionSkeleton rows={2} />
                    ) : alertsError ? (
                        <InlineSectionError message={alertsError} onRetry={retry} />
                    ) : triggeredAlerts.length > 0 ? (
                        <div className="space-y-3">
                            {triggeredAlerts.map((item) => (
                                <article className="min-w-0 rounded-lg border border-gray-700/50 bg-gray-900/50 p-3" key={item.id}>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <Badge variant="outline">{SEVERITY_LABELS[item.severity] ?? item.severity}</Badge>
                                        <span className="text-xs text-gray-500">{formatDateTime(item.createdAt)}</span>
                                    </div>
                                    <p className="mt-2 text-sm break-words text-gray-200">{item.title}</p>
                                    <p className="mt-1 text-xs break-words text-gray-400">{item.message}</p>
                                </article>
                            ))}
                            <p className="text-xs text-gray-500">
                                {alerts.length === 1 ? '1 regla activa' : `${alerts.length} reglas activas`} · el motor las evalúa cada 5 min.
                            </p>
                        </div>
                    ) : alerts.length > 0 ? (
                        <div className="space-y-2">
                            {alerts.slice(0, 3).map((alert) => (
                                <p className="min-w-0 break-words text-sm text-gray-300" key={alert._id}>
                                    {alertRuleLabel(alert)}
                                </p>
                            ))}
                            <p className="text-xs text-gray-500">
                                {alerts.length === 1 ? '1 regla activa' : `${alerts.length} reglas activas`} · ninguna se ha disparado todavía.
                            </p>
                        </div>
                    ) : (
                        <div className="text-center py-6">
                            <p className="text-gray-400 text-sm">{t('common.states.noAlerts')}</p>
                            <p className="text-gray-500 text-sm mt-2">{t('common.states.noAlertsHint')}</p>
                            <Link href="/alerts" className="mt-3 inline-flex min-h-[44px] items-center justify-center rounded-lg border border-teal-400/20 px-5 text-sm text-teal-400 transition-colors hover:text-teal-300">
                                Crear la primera alerta
                            </Link>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* 4 · Watchlist. */}
            <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-gray-700/50">
                    <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                        <Eye aria-hidden="true" className="h-5 w-5 text-yellow-400" />
                        Watchlist
                    </CardTitle>
                    <Link href="/watchlist" aria-label="Ver watchlist completa" className="inline-flex min-h-[44px] min-w-[44px] items-center justify-end px-1 text-yellow-400 hover:text-yellow-300 text-sm transition-colors">
                        <ArrowRight aria-hidden="true" className="w-4 h-4" />
                    </Link>
                </CardHeader>
                <CardContent className="pt-4">
                    {watchlistLoading ? (
                        <SectionSkeleton rows={3} />
                    ) : watchlistError ? (
                        <InlineSectionError message={watchlistError} onRetry={retry} />
                    ) : watchlist.length > 0 ? (
                        <div className="space-y-1">
                            {watchlist.map((stock) => (
                                <Link
                                    key={stock.symbol}
                                    href={`/research/${stock.symbol}`}
                                    prefetch
                                    className="flex min-h-[44px] items-center justify-between gap-2 p-3 bg-gray-900/30 rounded-lg hover:bg-gray-800/80 transition-colors group"
                                >
                                    <div className="flex min-w-0 items-center gap-3">
                                        <div className={`shrink-0 p-2 rounded-full ${stock.changePercent >= 0 ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                                            {stock.changePercent >= 0 ? <TrendingUp aria-hidden="true" className="h-4 w-4" /> : <TrendingDown aria-hidden="true" className="h-4 w-4" />}
                                        </div>
                                        <div className="min-w-0">
                                            <span className="block truncate text-white font-medium group-hover:text-yellow-400 transition-colors">{stock.symbol}</span>
                                            <p className="block truncate max-w-[140px] sm:max-w-none text-xs text-gray-500" title={stock.name}>{stock.name}</p>
                                        </div>
                                    </div>
                                    <div className="shrink-0 text-right">
                                        <div className="text-white font-mono">{formatMoney(stock.price)}</div>
                                        <div className={`text-xs ${stock.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {formatPercent(stock.changePercent, { fromRatio: false, digits: 2, signDisplay: 'always' })}
                                        </div>
                                    </div>
                                </Link>
                            ))}
                        </div>
                    ) : (
                        <div className="text-center py-8">
                            <p className="text-gray-400 text-sm">Lista vacía.</p>
                            {/* El buscador vive en el header (Ctrl+K) y en /search: el
                                inicio ya no es la puerta de entrada, así que el CTA
                                apunta allí y no a un "volver al inicio" circular. */}
                            <Link href="/search" className="inline-flex min-h-[44px] items-center justify-center text-yellow-400 text-xs mt-2 hover:underline">
                                Buscar acciones
                            </Link>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* 5 · Oportunidades por valor intrínseco. */}
            <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-gray-700/50">
                    <CardTitle className="text-lg text-gray-100 flex items-center gap-2">
                        <Gem aria-hidden="true" className="h-5 w-5 text-purple-400" />
                        Oportunidades por valor intrínseco (DCF)
                    </CardTitle>
                    <Link href="/screener" className="inline-flex min-h-[44px] items-center gap-1 px-2 -mr-2 text-purple-400 hover:text-purple-300 text-sm transition-colors">
                        <span className="whitespace-nowrap">Afinar con el Screener</span> <ArrowRight aria-hidden="true" className="w-4 h-4 shrink-0" />
                    </Link>
                </CardHeader>
                <CardContent className="pt-4">
                    {opportunitiesLoading ? (
                        <SectionSkeleton rows={2} />
                    ) : opportunitiesError ? (
                        <InlineSectionError message={opportunitiesError} onRetry={retry} />
                    ) : opportunities.length > 0 ? (
                        <>
                            <p className="mb-4 text-xs text-gray-500">
                                Todo el universo del screener (market cap &gt;{' '}
                                {formatCompact(MIN_MARKET_CAP, { maximumFractionDigits: 0 })}), sin filtro de sector.
                            </p>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                {opportunities.map((op) => (
                                    <Link key={op.symbol} href={`/research/${op.symbol}`} prefetch>
                                        <div className="p-4 bg-gray-900/40 rounded-xl border border-gray-700/30 hover:border-purple-500/50 hover:bg-gray-800 transition-all group">
                                            <div className="flex justify-between items-start mb-2">
                                                <div>
                                                    <h3 className="font-bold text-white group-hover:text-purple-400 transition-colors">{op.symbol}</h3>
                                                    <p className="text-xs text-gray-400">Precio: {formatMoney(op.price)}</p>
                                                </div>
                                                <Badge className="bg-green-900/30 text-green-400 border-green-800">
                                                    {formatPercent(op.upside, { fromRatio: false, digits: 1, signDisplay: 'always' })} potencial
                                                </Badge>
                                            </div>
                                            <div className="w-full bg-gray-800 h-1.5 rounded-full mt-2 overflow-hidden">
                                                <div
                                                    className="h-full bg-gradient-to-r from-green-600 to-green-400"
                                                    style={{ width: `${Math.min(op.upside, 100)}%` }}
                                                />
                                            </div>
                                            <p className="text-xs text-gray-500 mt-2 text-right">Valor justo: {formatMoney(op.fairValue)}</p>
                                        </div>
                                    </Link>
                                ))}
                            </div>
                        </>
                    ) : (
                        <p className="text-sm text-gray-500">
                            Ninguna empresa del universo supera hoy un 5 % de potencial sobre su valor intrínseco.
                        </p>
                    )}
                </CardContent>
            </Card>

            {/* 6 · Índices: contexto de mercado, no prioridad. Van al final y
                lo dicen, porque /screener los vuelve a pintar en "Índices y macro". */}
            <section>
                <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                    <h2 className="text-lg font-semibold text-gray-100">Contexto de mercado</h2>
                    <p className="text-xs text-gray-500">Referencia del día, no una sección de decisión.</p>
                </div>
                {indicesLoading ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5 gap-4">
                        {[1, 2, 3, 4].map((i) => (
                            <SectionSkeleton className="rounded-lg border border-gray-700 p-4" key={i} rows={1} />
                        ))}
                    </div>
                ) : indicesError ? (
                    <InlineSectionError message={indicesError} onRetry={retry} />
                ) : marketIndices.length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5 gap-4">
                        {marketIndices.map((index) => (
                            <MarketIndexCard key={index.symbol} index={index} />
                        ))}
                    </div>
                ) : (
                    <p className="text-sm text-gray-500">Sin datos de índices ahora mismo.</p>
                )}
            </section>
        </div>
    );
}

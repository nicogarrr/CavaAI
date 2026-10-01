'use client';

/**
 * Velas japonesas + volumen con lightweight-charts v5 (TradingView, canvas).
 *
 * ESM-only + Next 16: la librería NUNCA se importa estáticamente aquí (ni
 * `import type` con valor en runtime); se carga con `import()` dentro del
 * efecto y este fichero solo llega al cliente vía `dynamic(ssr: false)`
 * desde `CompanyMarketPanel`. El gráfico se crea UNA vez y los datos se
 * actualizan con `setData` (recrearlo en cada render pierde el zoom y fuga
 * listeners: `chart.remove()` en la limpieza).
 *
 * Tema dark-only con los tokens de `app/globals.css` (good/bad para las
 * velas, tinta secundaria para el texto). Sin OHLC no hay velas inventadas:
 * estado vacío explícito con el motivo.
 */

import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';

import {
    formatCompact,
    formatMarketDate,
    formatMoney,
    formatNumber,
    isValidCurrencyCode,
    NA,
} from '@/lib/format';
import {
    CANDLES_INTERVAL_LABEL,
    TRADINGVIEW_URL,
    summarizeCandles,
    toCandleRows,
    toCandlestickData,
    toVolumeData,
    type CandleRow,
    type MarketHistoryPoint,
} from '@/lib/market/candles';
import type { CompanyMarketSnapshot } from '@/lib/actions/market-workspace.actions';
import type { CandlestickData, HistogramData, IChartApi, ISeriesApi, MouseEventParams, Time } from 'lightweight-charts';

function money(value: number | null, currency: string | null | undefined): string {
    if (value == null) return NA;
    // Sin divisa verificada del listado, número pelado: nunca un USD asumido (F380).
    return isValidCurrencyCode(currency) ? formatMoney(value, currency) : formatNumber(value);
}

function cssVar(name: string, fallback: string): string {
    if (typeof window === 'undefined') return fallback;
    try {
        const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return value || fallback;
    } catch {
        return fallback;
    }
}

function attributionSummary(count: number, lastClose: string, lastDate: string): string {
    return `Velas ${CANDLES_INTERVAL_LABEL}s: ${count} sesiones. Último cierre ${lastClose} (${lastDate}). Datos diarios con retraso.`;
}

/** Gráfico de velas: se carga solo en cliente (dynamic ssr:false desde el panel) */
export default function CompanyMarketChart({
    history,
    currency,
}: {
    history: CompanyMarketSnapshot['history'];
    currency?: string | null;
}) {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const candleSeriesRef = useRef<ISeriesApi<'Candlestick', Time> | null>(null);
    const volumeSeriesRef = useRef<ISeriesApi<'Histogram', Time> | null>(null);
    const rowsByTimeRef = useRef<Map<string, CandleRow>>(new Map());
    const [chartState, setChartState] = useState<'loading' | 'ready' | 'error'>('loading');
    const [hovered, setHovered] = useState<CandleRow | null>(null);

    const rows = useMemo(() => toCandleRows((history ?? []) as MarketHistoryPoint[]), [history]);
    const summary = useMemo(() => summarizeCandles(rows), [rows]);
    const historyLength = history?.length ?? 0;

    // Sin OHLC no hay velas que pintar: estado vacío honesto con el motivo
    // (nunca un chart vacío que parezca plano ni velas O=H=L=C inventadas).
    if (rows.length === 0) {
        return (
            <div
                className="rounded-lg border border-amber-900/60 bg-amber-950/20 p-6 text-sm leading-6 text-amber-200"
                role="status"
            >
                {historyLength === 0 ? (
                    <>Historial de precio no disponible. El workspace muestra este estado de forma explícita y no inventa ningún gráfico.</>
                ) : (
                    <>
                        Velas no disponibles: la serie recibida trae {historyLength} sesiones con cierre
                        pero sin apertura, máximo ni mínimo, y sin OHLC no se pueden dibujar velas.
                    </>
                )}
                <p className="mt-2 text-xs text-amber-200/70">
                    Gráficos por{' '}
                    <a className="underline hover:text-amber-100" href={TRADINGVIEW_URL} rel="noreferrer" target="_blank">
                        TradingView
                    </a>
                    .
                </p>
            </div>
        );
    }

    const last = rows[rows.length - 1];
    const shown: CandleRow = hovered ?? last;
    const bullish = shown.close >= shown.open;
    const ariaLabel = summary
        ? `Velas ${CANDLES_INTERVAL_LABEL}s de ${summary.count} sesiones, del ${formatMarketDate(summary.firstTime)} al ${formatMarketDate(summary.lastTime)}. ` +
          `Último cierre ${money(summary.lastClose, currency)} (${formatMarketDate(summary.lastTime)}). ` +
          `Variación en el periodo ${summary.change >= 0 ? '+' : ''}${formatNumber(summary.change)} ` +
          `(${summary.changePercent == null ? NA : `${summary.changePercent >= 0 ? '+' : ''}${formatNumber(summary.changePercent)} %`}). ` +
          `Rango ${money(summary.rangeLow, currency)} – ${money(summary.rangeHigh, currency)}. ` +
          (summary.knownVolumeSessions === 0
              ? 'Volumen no disponible en esta serie.'
              : `Volumen conocido en ${summary.knownVolumeSessions} de ${summary.count} sesiones.`) +
          ' Datos diarios con retraso.'
        : attributionSummary(rows.length, money(last.close, currency), formatMarketDate(last.time));

    return (
        <div className="w-full max-w-full overflow-hidden">
            {/* Leyenda en vivo: el canvas no es leíble por lector de pantalla;
                esta fila sí (y sirve de tooltip visible del crosshair). */}
            <div
                aria-live="off"
                className="mb-2 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500"
                data-testid="candles-legend"
            >
                <span className="font-medium text-gray-400">{formatMarketDate(shown.time)}</span>
                <span>
                    A: <span className="text-gray-400">{money(shown.open, currency)}</span>
                </span>
                <span>
                    Máx: <span className="text-gray-400">{money(shown.high, currency)}</span>
                </span>
                <span>
                    Mín: <span className="text-gray-400">{money(shown.low, currency)}</span>
                </span>
                <span>
                    Cierre:{' '}
                    <span className={bullish ? 'font-semibold text-teal-300' : 'font-semibold text-red-300'}>
                        {money(shown.close, currency)}
                    </span>
                </span>
                <span>
                    Vol: <span className="text-gray-400">{shown.volume == null ? NA : formatCompact(shown.volume)}</span>
                </span>
            </div>
            <div
                ref={containerRef}
                aria-label={ariaLabel}
                className="h-[280px] w-full sm:h-[420px]"
                data-testid="candles-chart"
                role="img"
            >
                {chartState === 'loading' ? (
                    <div
                        aria-label="Cargando gráfico de velas"
                        className="h-full w-full animate-pulse rounded-lg border border-gray-800 bg-gray-900/40"
                        role="status"
                    />
                ) : null}
                {chartState === 'error' ? (
                    <div className="rounded-lg border border-red-900/60 bg-red-950/20 p-6 text-sm text-red-200" role="alert">
                        No se pudo cargar el gráfico interactivo de velas. El resto de la ficha sigue disponible.
                    </div>
                ) : null}
            </div>
            <p className="mt-2 text-xs leading-5 text-gray-500">
                {summary ? (
                    <>
                        {summary.count} sesiones · {formatMarketDate(summary.firstTime)} – {formatMarketDate(summary.lastTime)} · intervalo{' '}
                        {CANDLES_INTERVAL_LABEL} · Datos diarios con retraso
                        {summary.knownVolumeSessions === 0 ? ' · Volumen no disponible en esta serie' : null} · Gráficos por{' '}
                    </>
                ) : (
                    <>Gráficos por </>
                )}
                <a className="underline underline-offset-4 hover:text-teal-400" href={TRADINGVIEW_URL} rel="noreferrer" target="_blank">
                    TradingView
                </a>
                .
            </p>
            <ChartEngine
                containerRef={containerRef}
                chartRef={chartRef}
                candleSeriesRef={candleSeriesRef}
                volumeSeriesRef={volumeSeriesRef}
                rowsByTimeRef={rowsByTimeRef}
                rows={rows}
                currency={currency}
                onHover={setHovered}
                onState={setChartState}
            />
        </div>
    );
}

function ChartEngine({
    containerRef,
    chartRef,
    candleSeriesRef,
    volumeSeriesRef,
    rowsByTimeRef,
    rows,
    currency,
    onHover,
    onState,
}: {
    containerRef: RefObject<HTMLDivElement | null>;
    chartRef: RefObject<IChartApi | null>;
    candleSeriesRef: RefObject<ISeriesApi<'Candlestick', Time> | null>;
    volumeSeriesRef: RefObject<ISeriesApi<'Histogram', Time> | null>;
    rowsByTimeRef: RefObject<Map<string, CandleRow>>;
    rows: CandleRow[];
    currency?: string | null;
    onHover: (row: CandleRow | null) => void;
    onState: (state: 'loading' | 'ready' | 'error') => void;
}) {
    const rowsRef = useRef(rows);
    rowsRef.current = rows;
    const currencyRef = useRef(currency);
    currencyRef.current = currency;

    // Creación única del gráfico (efecto sin dependencias: montar una vez).
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;
        let disposed = false;
        let chart: IChartApi | null = null;
        let handler: ((param: MouseEventParams<Time>) => void) | null = null;

        (async () => {
            try {
                const { CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, createChart } =
                    await import('lightweight-charts');
                if (disposed || containerRef.current == null) return;

                const up = cssVar('--color-good', '#5eead4');
                const down = cssVar('--color-bad', '#fca5a5');
                const ink = cssVar('--color-gray-500', '#a1a1aa');
                const grid = '#27272a';
                const code = typeof currencyRef.current === 'string' ? currencyRef.current : null;
                const priceFormatter = isValidCurrencyCode(code)
                    ? (price: number) => formatMoney(price, code as string)
                    : (price: number) => formatNumber(price);

                chart = createChart(container, {
                    autoSize: true,
                    height: container.clientHeight || 280,
                    layout: {
                        background: { type: ColorType.Solid, color: 'transparent' },
                        textColor: ink,
                        fontFamily:
                            'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                        fontSize: 11,
                        attributionLogo: true,
                    },
                    grid: { vertLines: { color: grid }, horzLines: { color: grid } },
                    crosshair: {
                        mode: CrosshairMode.Normal,
                        vertLine: { color: '#3f3f46', labelBackgroundColor: '#27272a' },
                        horzLine: { color: '#3f3f46', labelBackgroundColor: '#27272a' },
                    },
                    rightPriceScale: { borderVisible: false },
                    timeScale: { borderVisible: false, rightOffset: 4 },
                    localization: { locale: 'es-ES' },
                });

                const candles = chart.addSeries(CandlestickSeries, {
                    upColor: up,
                    downColor: down,
                    wickUpColor: up,
                    wickDownColor: down,
                    borderVisible: false,
                    priceFormat: { type: 'custom', minMove: 0.01, formatter: priceFormatter },
                });
                candleSeriesRef.current = candles;

                const current = rowsRef.current;
                rowsByTimeRef.current = new Map(current.map((row) => [row.time, row]));
                candles.setData(toCandlestickData(current) as CandlestickData<Time>[]);

                const volumes = toVolumeData(current, { up: 'rgba(94,234,212,0.45)', down: 'rgba(252,165,165,0.45)' });
                if (volumes.length > 0) {
                    const volume = chart.addSeries(
                        HistogramSeries,
                        { priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false },
                        1,
                    );
                    volumeSeriesRef.current = volume;
                    volume.setData(volumes as HistogramData<Time>[]);
                    chart.panes()[1]?.setHeight(110);
                }

                handler = (param: MouseEventParams<Time>) => {
                    if (param.time === undefined) {
                        onHover(null);
                        return;
                    }
                    const point = param.seriesData.get(candles) as CandlestickData<Time> | undefined;
                    const time = typeof point?.time === 'string' ? point.time : typeof param.time === 'string' ? param.time : null;
                    onHover(time ? (rowsByTimeRef.current.get(time) ?? null) : null);
                };
                chart.subscribeCrosshairMove(handler);
                chart.timeScale().fitContent();

                chartRef.current = chart;
                if (!disposed) onState('ready');
            } catch {
                if (!disposed) onState('error');
            }
        })();

        return () => {
            disposed = true;
            if (chart && handler) chart.unsubscribeCrosshairMove(handler);
            chart?.remove();
            chartRef.current = null;
            candleSeriesRef.current = null;
            volumeSeriesRef.current = null;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Actualización de datos sin recrear el gráfico (históricos largos: solo setData).
    useEffect(() => {
        const chart = chartRef.current;
        const candles = candleSeriesRef.current;
        if (!chart || !candles || rows.length === 0) return;
        rowsByTimeRef.current = new Map(rows.map((row) => [row.time, row]));
        candles.setData(toCandlestickData(rows) as CandlestickData<Time>[]);
        const volumes = toVolumeData(rows, { up: 'rgba(94,234,212,0.45)', down: 'rgba(252,165,165,0.45)' });
        if (volumeSeriesRef.current) {
            volumeSeriesRef.current.setData(volumes as HistogramData<Time>[]);
        }
        onHover(null);
    }, [rows, chartRef, candleSeriesRef, volumeSeriesRef, rowsByTimeRef, onHover]);

    return null;
}

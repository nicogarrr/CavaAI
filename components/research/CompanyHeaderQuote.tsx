import { NA, formatMarketDate, formatMoney, formatNumber, formatPercent, isValidCurrencyCode } from '@/lib/format';
import { SPARK_HEIGHT, SPARK_WIDTH, sparklinePoints } from '@/lib/sparkline';
import type { CompanyMarketSnapshot } from '@/lib/actions/market-workspace.actions';

const SPARK_SESSIONS = 30;
const SHORT_DATE: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' };

/**
 * Precio + variación + sparkline de la cabecera de la ficha. Servidor puro
 * (SVG, sin JS de cliente). Reglas de honestidad:
 * - precio ausente se omite; métricas ausentes usan N/D, nunca se fabrican;
 * - sin divisa verificada no se muestra precio (nunca se asume USD);
 * - un precio que viene del último cierre de vela se rotula con su fecha
 *   («Cierre del …») para que no parezca cotización actual;
 * - el sparkline muestra el rango de fechas que dibuja.
 */
export function CompanyHeaderQuote({ snapshot }: { snapshot: CompanyMarketSnapshot }) {
    const { quote, currency, history } = snapshot;
    const hasDatedMetrics = !!quote.metricsSource && !!quote.metricsSession;
    const showPrice = quote.price != null && isValidCurrencyCode(currency);
    if (!showPrice && history.length === 0) return null;
    const sessions = history.slice(-SPARK_SESSIONS);
    const points = sparklinePoints(sessions.map((point) => point.close));
    const firstDate = sessions[0]?.date ?? null;
    const lastDate = sessions[sessions.length - 1]?.date ?? null;
    // Signo coherente con el dato mostrado: si falta change, manda
    // changePercent; sin ninguno, no hay linea de variacion que colorear.
    const signBase = quote.change ?? quote.changePercent ?? 0;
    return (
        <div className="flex w-full flex-col gap-4" data-testid="company-header-quote">
            {showPrice ? (
                <div>
                    {quote.priceAsOf ? (
                        <p className="text-[11px] uppercase tracking-wide text-gray-500">
                            Cierre del {formatMarketDate(quote.priceAsOf, SHORT_DATE)}
                        </p>
                    ) : quote.priceKind === 'close' ? (
                        <p className="text-[11px] uppercase tracking-wide text-gray-500">
                            Precio de fecha desconocida
                        </p>
                    ) : null}
                    <div className="text-4xl font-semibold tracking-tight text-gray-100 sm:text-5xl">
                        {formatMoney(quote.price, currency)}
                    </div>
                    {quote.change != null || quote.changePercent != null ? (
                        <div className={`mt-2 inline-flex w-fit items-center rounded-full px-2.5 py-1 text-sm font-medium ${signBase > 0 ? 'bg-emerald-500/10 text-emerald-300' : signBase < 0 ? 'bg-red-500/10 text-red-300' : 'bg-gray-800 text-gray-300'}`}>
                            {[
                                quote.change != null
                                    ? formatNumber(quote.change, { signDisplay: 'always', maximumFractionDigits: 2 })
                                    : null,
                                quote.changePercent != null
                                    ? formatPercent(quote.changePercent, { fromRatio: false, digits: 2, signDisplay: 'always' })
                                    : null,
                            ]
                                .filter(Boolean)
                                .join(' · ')}
                        </div>
                    ) : null}
                </div>
            ) : null}
            {showPrice ? (
                <div className="overflow-x-auto">
                <dl className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-gray-800 border-y border-gray-800" data-testid="company-metric-strip">
                    {[
                        ['Apertura', hasDatedMetrics ? quote.open : null], ['Máximo', hasDatedMetrics ? quote.high : null],
                        ['Mínimo', hasDatedMetrics ? quote.low : null], ['Cierre anterior', null],
                    ].map(([label, value]) => (
                        <div className="min-w-0 px-2 py-3 first:pl-0 sm:px-3" key={String(label)}>
                            <dt className="text-xs text-gray-500">{label}</dt>
                            <dd className="mt-1 text-sm font-medium text-gray-200">{value == null ? NA : formatMoney(value as number, currency)}</dd>
                        </div>
                    ))}
                </dl>
                {hasDatedMetrics ? <p className="mt-2 text-xs text-gray-500">Fuente: {quote.metricsSource} · Sesión del {formatMarketDate(quote.metricsSession, SHORT_DATE)}</p> : null}
                </div>
            ) : null}
            {points && firstDate && lastDate ? (
                <>
                    <svg
                        aria-label={`Evolución del precio del ${formatMarketDate(firstDate, SHORT_DATE)} al ${formatMarketDate(lastDate, SHORT_DATE)}`}
                        className="mt-1 inline-block h-9 w-[120px]"
                        role="img"
                        viewBox={`0 0 ${SPARK_WIDTH} ${SPARK_HEIGHT}`}
                    >
                        <polyline
                            fill="none"
                            points={points}
                            stroke="#5eead4"
                            strokeWidth="1.5"
                        />
                    </svg>
                    <p className="text-[10px] text-gray-500">
                        {formatMarketDate(firstDate, SHORT_DATE)} – {formatMarketDate(lastDate, SHORT_DATE)}
                    </p>
                </>
            ) : null}
        </div>
    );
}

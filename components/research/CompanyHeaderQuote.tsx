import { formatMarketDate, formatMoney, formatNumber, formatPercent, isValidCurrencyCode, NA } from '@/lib/format';
import { SPARK_HEIGHT, SPARK_WIDTH, sparklinePoints } from '@/lib/sparkline';
import type { CompanyMarketSnapshot } from '@/lib/actions/market-workspace.actions';

const SPARK_SESSIONS = 30;
const SHORT_DATE: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' };

/**
 * Precio + variación + sparkline de la cabecera de la ficha. Servidor puro
 * (SVG, sin JS de cliente). Reglas de honestidad:
 * - cada dato ausente se omite, nunca se fabrica;
 * - sin divisa verificada no se muestra precio (nunca se asume USD);
 * - un precio que viene del último cierre de vela se rotula con su fecha
 *   («Cierre del …») para que no parezca cotización actual;
 * - el sparkline muestra el rango de fechas que dibuja.
 */
export function CompanyHeaderQuote({ snapshot }: { snapshot: CompanyMarketSnapshot }) {
    const { quote, currency, history } = snapshot;
    const showPrice = quote.price != null && isValidCurrencyCode(currency);
    if (!showPrice && history.length === 0) return null;
    const sessions = history.slice(-SPARK_SESSIONS);
    const points = sparklinePoints(sessions.map((point) => point.close));
    const firstDate = sessions[0]?.date ?? null;
    const lastDate = sessions[sessions.length - 1]?.date ?? null;
    const positive = (quote.change ?? 0) >= 0;
    return (
        <div className="sm:ml-auto sm:text-right">
            {showPrice ? (
                <>
                    {quote.priceAsOf ? (
                        <p className="text-[11px] uppercase tracking-wide text-gray-500">
                            Cierre del {formatMarketDate(quote.priceAsOf, SHORT_DATE)}
                        </p>
                    ) : null}
                    <div className="text-2xl font-bold text-gray-100 sm:text-3xl">
                        {formatMoney(quote.price, currency)}
                    </div>
                    <div className={positive ? 'text-sm text-teal-300' : 'text-sm text-red-300'}>
                        {quote.change == null
                            ? NA
                            : formatNumber(quote.change, { signDisplay: 'always', maximumFractionDigits: 2 })}
                        {' · '}
                        {quote.changePercent == null
                            ? NA
                            : formatPercent(quote.changePercent, { fromRatio: false, digits: 2, signDisplay: 'always' })}
                    </div>
                </>
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
                            stroke={positive ? '#5eead4' : '#f87171'}
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

import { formatMoney, formatNumber, formatPercent, NA } from '@/lib/format';
import { SPARK_HEIGHT, SPARK_WIDTH, sparklinePoints } from '@/lib/sparkline';
import type { CompanyMarketSnapshot } from '@/lib/actions/market-workspace.actions';

// Intl solo acepta códigos ISO 4217; un valor raro del backend no debe
// romper la cabecera (fallback USD, la moneda mayoritaria del universo).
function safeCurrency(currency: string | null): string {
    return currency && /^[A-Z]{3}$/.test(currency) ? currency : 'USD';
}

function money(value: number | null, currency: string | null) {
    return value == null ? NA : formatMoney(value, safeCurrency(currency));
}

const SPARK_SESSIONS = 30;

/**
 * Precio + variación + sparkline de la cabecera de la ficha. Servidor puro
 * (SVG, sin JS de cliente). Cada dato ausente se omite, nunca se fabrica.
 */
export function CompanyHeaderQuote({ snapshot }: { snapshot: CompanyMarketSnapshot }) {
    const { quote, currency, history } = snapshot;
    if (quote.price == null && history.length === 0) return null;
    const positive = (quote.change ?? 0) >= 0;
    const closes = history.slice(-SPARK_SESSIONS).map((point) => point.close);
    const points = sparklinePoints(closes);
    return (
        <div className="sm:ml-auto sm:text-right">
            {quote.price != null ? (
                <>
                    <div className="text-2xl font-bold text-gray-100 sm:text-3xl">
                        {money(quote.price, currency)}
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
            {points ? (
                <svg
                    aria-label={`Evolución del precio en las últimas ${closes.length} sesiones`}
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
            ) : null}
        </div>
    );
}

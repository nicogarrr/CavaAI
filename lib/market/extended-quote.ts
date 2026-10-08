import type { components } from '@/lib/research/openapi.generated';
export type ExtendedQuote = components['schemas']['ExtendedQuote'];

const clock = (timestamp: number) => new Intl.DateTimeFormat('es-ES', {
    timeZone: 'Europe/Madrid', hour: '2-digit', minute: '2-digit', hour12: false,
}).format(new Date(timestamp * 1000));
const day = (date: string) => new Intl.DateTimeFormat('es-ES', {
    timeZone: 'UTC', day: 'numeric', month: 'short',
}).format(new Date(`${date}T12:00:00Z`));

export function extendedQuoteLabel(quote: ExtendedQuote | null): string {
    if (!quote?.source || !quote.timestamp || quote.price == null || quote.status === 'unavailable') return 'N/D';
    const time = clock(quote.timestamp);
    const priceSession = quote.price_session;
    if (!priceSession || priceSession === 'cerrado') return 'N/D';
    const sameSession = quote.session === priceSession;
    const sessionLabel = priceSession === 'pre' ? 'Premercado'
        : priceSession === 'post' ? 'Post-cierre' : 'Mercado abierto';
    let label: string;
    if (sameSession) {
        label = `${sessionLabel} · ${time}`;
    } else {
        if (!quote.trading_date) return 'N/D';
        const datedLabel = priceSession === 'post' ? 'Último post-cierre del'
            : priceSession === 'pre' ? 'Último premercado del'
            : quote.regular_close_timestamp === quote.timestamp ? 'Cierre del' : 'Último precio regular del';
        label = `${datedLabel} ${day(quote.trading_date)} · ${time}`;
    }
    return quote.status === 'retrasado' ? `${label} · Retrasado` : label;
}

export function quoteTime(timestamp: number | null | undefined): string {
    return timestamp ? clock(timestamp) : 'N/D';
}

export function quoteDate(timestamp: number | null | undefined): string {
    return timestamp ? new Intl.DateTimeFormat('es-ES', {
        timeZone: 'Europe/Madrid', day: 'numeric', month: 'short',
    }).format(new Date(timestamp * 1000)) : 'N/D';
}

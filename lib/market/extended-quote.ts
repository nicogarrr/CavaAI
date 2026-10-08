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
    const label = quote.session === 'cerrado'
        ? quote.trading_date ? `Cierre del ${day(quote.trading_date)} · ${time}` : 'N/D'
        : quote.session === 'pre' ? `Premercado · ${time}`
        : quote.session === 'post' ? `Post-cierre · ${time}` : `Mercado abierto · ${time}`;
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

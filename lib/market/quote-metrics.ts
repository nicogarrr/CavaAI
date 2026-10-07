/** Metadatos de la misma cotización saneada. No se toman de la serie de velas. */
type QuoteInput = {
    source?: 'Finnhub' | 'Yahoo Finance';
    t?: number | null;
    o?: number; h?: number; l?: number; pc?: number;
};

export function datedQuoteMetrics(quote: QuoteInput | null, quoteUsable: boolean) {
    const absent = { open: null, high: null, low: null, previousClose: null, source: null, timestamp: null };
    if (!quoteUsable || !quote || quote.source !== 'Finnhub'
        || typeof quote.t !== 'number' || !Number.isFinite(quote.t) || quote.t <= 0) return absent;
    const price = (value: unknown) => typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null;
    return {
        open: price(quote.o), high: price(quote.h), low: price(quote.l),
        // Finnhub pc no trae fecha propia de la sesión anterior: no le asignamos la del t actual.
        previousClose: null,
        source: quote.source, timestamp: quote.t,
    };
}

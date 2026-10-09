/** Timestamped extended quote for the strictly gated, deterministic UI E2E. */
import type { ExtendedQuote } from '@/lib/market/extended-quote';

export function e2eExtendedQuoteFixture(ticker: string): ExtendedQuote {
    const timestamp = Date.UTC(2026, 8, 9, 15, 0) / 1000;
    return {
        ticker, status: 'available', session: 'regular', price_session: 'regular',
        price: 336.56, timestamp, currency: 'USD', source: 'Fixture local',
        fetched_at: timestamp, trading_date: '2026-09-09',
        previous_close: 334.22, previous_close_timestamp: null,
        change: 2.34, change_percent: 0.7,
        regular_close: null, regular_close_timestamp: null,
        open: 334.2, high: 337.1, low: 333.8,
        metrics_timestamp: timestamp, metrics_session: '2026-09-09',
    };
}

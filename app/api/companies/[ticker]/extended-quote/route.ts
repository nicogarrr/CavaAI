import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { isE2EMarketFixtureEnabled } from '@/lib/e2e-market-fixture';
import { e2eExtendedQuoteFixture } from '@/lib/e2e-extended-quote-fixture';
import { researchRequest } from '@/lib/research/client';
import type { ExtendedQuote } from '@/lib/market/extended-quote';

export async function GET(_request: Request, { params }: { params: Promise<{ ticker: string }> }) {
    await requireAuthenticatedUser();
    const { ticker } = await params;
    if (!/^[A-Za-z0-9.^=-]{1,32}$/.test(ticker)) return Response.json({ status: 'unavailable' }, { status: 400 });
    // Same exact gate as the server market/history fixture. No live Yahoo
    // request in deterministic E2E, and no fictitious production fallback.
    if (isE2EMarketFixtureEnabled(process.env, ticker)) {
        return Response.json(e2eExtendedQuoteFixture(ticker), { headers: { 'Cache-Control': 'no-store' } });
    }
    try {
        const quote = await researchRequest<ExtendedQuote>(`/api/companies/${encodeURIComponent(ticker)}/extended-quote`);
        return Response.json(quote, { headers: { 'Cache-Control': 'no-store' } });
    } catch {
        return Response.json({ status: 'unavailable' }, { status: 502, headers: { 'Cache-Control': 'no-store' } });
    }
}

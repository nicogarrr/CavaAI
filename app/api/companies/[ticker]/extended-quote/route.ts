import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchRequest } from '@/lib/research/client';
import type { ExtendedQuote } from '@/lib/market/extended-quote';

export async function GET(_request: Request, { params }: { params: Promise<{ ticker: string }> }) {
    await requireAuthenticatedUser();
    const { ticker } = await params;
    if (!/^[A-Za-z0-9.^=-]{1,32}$/.test(ticker)) return Response.json({ status: 'unavailable' }, { status: 400 });
    try {
        const quote = await researchRequest<ExtendedQuote>(`/api/companies/${encodeURIComponent(ticker)}/extended-quote`);
        return Response.json(quote, { headers: { 'Cache-Control': 'no-store' } });
    } catch {
        return Response.json({ status: 'unavailable' }, { status: 502, headers: { 'Cache-Control': 'no-store' } });
    }
}

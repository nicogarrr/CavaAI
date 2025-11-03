import { NextRequest, NextResponse } from 'next/server';
import { getProfile } from '@/lib/actions/finnhub.actions';

export async function GET(request: NextRequest) {
    try {
        const searchParams = request.nextUrl.searchParams;
        const symbol = searchParams.get('symbol');

        if (!symbol) {
            return NextResponse.json(
                { error: 'Symbol parameter is required' },
                { status: 400 }
            );
        }

        // Obtener precio actual desde Finnhub
        const token = process.env.FINNHUB_API_KEY ?? process.env.NEXT_PUBLIC_FINNHUB_API_KEY;
        if (!token) {
            return NextResponse.json(
                { error: 'FINNHUB API key not configured' },
                { status: 500 }
            );
        }

        const quoteUrl = `https://finnhub.io/api/v1/quote?symbol=${encodeURIComponent(symbol.toUpperCase())}&token=${token}`;
        const response = await fetch(quoteUrl, {
            cache: 'no-store',
            next: { revalidate: 60 }, // Revalidar cada minuto
        });

        if (!response.ok) {
            return NextResponse.json(
                { error: 'Failed to fetch quote' },
                { status: response.status }
            );
        }

        const quote = await response.json();
        
        return NextResponse.json({
            currentPrice: quote.c || quote.price || 0,
            change: quote.d || 0,
            changePercent: quote.dp || 0,
            high: quote.h || 0,
            low: quote.l || 0,
            open: quote.o || 0,
            previousClose: quote.pc || 0,
        });
    } catch (error) {
        // Log detailed error server-side for debugging
        if (process.env.NODE_ENV === 'development') {
            console.error('Quote API Error:', error);
        }
        
        // Return generic error to client to avoid leaking sensitive information
        return NextResponse.json(
            { error: 'Failed to fetch quote data. Please try again later.' },
            { status: 500 }
        );
    }
}


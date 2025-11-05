import { NextRequest, NextResponse } from 'next/server';
import { env } from '@/lib/env';
import { SYMBOL_VALIDATION, ERROR_MESSAGES, CACHE_TTL } from '@/lib/constants';
import { ValidationError, ExternalAPIError, toAppError } from '@/lib/types/errors';
import { getQuoteWithFallback } from '@/lib/actions/dataSources.actions';

/**
 * Valida el formato del símbolo
 */
function validateSymbol(symbol: string): void {
    if (!symbol || symbol.trim().length === 0) {
        throw new ValidationError('Symbol parameter is required');
    }

    const trimmedSymbol = symbol.trim().toUpperCase();
    
    if (trimmedSymbol.length < SYMBOL_VALIDATION.MIN_LENGTH || 
        trimmedSymbol.length > SYMBOL_VALIDATION.MAX_LENGTH) {
        throw new ValidationError(
            `Symbol must be between ${SYMBOL_VALIDATION.MIN_LENGTH} and ${SYMBOL_VALIDATION.MAX_LENGTH} characters`
        );
    }

    if (!SYMBOL_VALIDATION.PATTERN.test(trimmedSymbol)) {
        throw new ValidationError(ERROR_MESSAGES.INVALID_SYMBOL);
    }
}

export async function GET(request: NextRequest) {
    try {
        const searchParams = request.nextUrl.searchParams;
        const symbol = searchParams.get('symbol');

        // Validar símbolo
        if (!symbol) {
            return NextResponse.json(
                { error: ERROR_MESSAGES.VALIDATION_ERROR, details: 'Symbol parameter is required' },
                { status: 400 }
            );
        }

        validateSymbol(symbol);

        // Usar solo variable de servidor, nunca NEXT_PUBLIC_*
        const token = env.FINNHUB_API_KEY;
        if (!token) {
            // Intentar con fallback automático
            const quoteData = await getQuoteWithFallback(symbol.toUpperCase());
            
            if (!quoteData) {
                return NextResponse.json(
                    { error: ERROR_MESSAGES.MISSING_API_KEY },
                    { status: 503 }
                );
            }

            return NextResponse.json({
                currentPrice: quoteData.currentPrice,
                change: quoteData.change || 0,
                changePercent: quoteData.changePercent || 0,
                high: quoteData.high || 0,
                low: quoteData.low || 0,
                open: quoteData.open || 0,
                previousClose: quoteData.previousClose || 0,
            });
        }

        const quoteUrl = `https://finnhub.io/api/v1/quote?symbol=${encodeURIComponent(symbol.toUpperCase())}&token=${token}`;
        const response = await fetch(quoteUrl, {
            next: { revalidate: CACHE_TTL.REALTIME_DATA }, // Cache consistente
        });

        if (!response.ok) {
            // Si Finnhub falla, intentar fallback
            if (response.status === 429 || response.status >= 500) {
                const quoteData = await getQuoteWithFallback(symbol.toUpperCase());
                if (quoteData) {
                    return NextResponse.json({
                        currentPrice: quoteData.currentPrice,
                        change: quoteData.change || 0,
                        changePercent: quoteData.changePercent || 0,
                        high: quoteData.high || 0,
                        low: quoteData.low || 0,
                        open: quoteData.open || 0,
                        previousClose: quoteData.previousClose || 0,
                    });
                }
            }

            return NextResponse.json(
                { error: ERROR_MESSAGES.EXTERNAL_API_ERROR },
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
    } catch (error: unknown) {
        const appError = toAppError(error);
        
        // Log detallado solo en desarrollo
        if (env.NODE_ENV === 'development') {
            console.error('Quote API Error:', appError);
        }
        
        // Retornar mensaje genérico al cliente para evitar filtrar información sensible
        if (appError instanceof ValidationError) {
            return NextResponse.json(
                { error: appError.message },
                { status: 400 }
            );
        }

        return NextResponse.json(
            { error: ERROR_MESSAGES.EXTERNAL_API_ERROR },
            { status: 500 }
        );
    }
}


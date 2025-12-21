import { NextRequest, NextResponse } from 'next/server';
import { getSessionCookie } from "better-auth/cookies";
import { getAuth } from "@/lib/better-auth/auth";
import { rateLimit } from "@/lib/utils/rateLimit";
import { RATE_LIMITS } from "@/lib/constants";

/**
 * Middleware mejorado que valida sesión real y aplica rate limiting
 */
export async function middleware(request: NextRequest) {
    // Rate limiting para prevenir abuso
    const ip = request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || request.headers.get('x-real-ip') || 'unknown';
    const rateLimitResult = rateLimit(
        ip,
        60 * 1000, // 1 minuto
        RATE_LIMITS.API_ROUTE.limit
    );

    if (!rateLimitResult.allowed) {
        return NextResponse.json(
            { error: 'Rate limit exceeded. Please try again later.' },
            { 
                status: 429,
                headers: {
                    'X-RateLimit-Limit': RATE_LIMITS.API_ROUTE.limit.toString(),
                    'X-RateLimit-Remaining': rateLimitResult.remaining.toString(),
                    'X-RateLimit-Reset': new Date(rateLimitResult.resetAt).toISOString(),
                },
            }
        );
    }

    // Verificar cookie de sesión
    const sessionCookie = getSessionCookie(request);

    if (!sessionCookie) {
        return NextResponse.redirect(new URL('/sign-in', request.url));
    }

    // Validar sesión real con Better Auth
    try {
        const auth = await getAuth();
        if (auth) {
            // Verificar que la sesión es válida
            // Better Auth valida automáticamente las cookies, pero podemos hacer una verificación adicional
            const session = await auth.api.getSession({ headers: request.headers });
            
            if (!session) {
                // Sesión inválida, redirigir a sign-in
                const response = NextResponse.redirect(new URL('/sign-in', request.url));
                // Eliminar cookie inválida
                response.cookies.delete('better-auth.session_token');
                return response;
            }
        }
    } catch (error) {
        // Si hay error validando la sesión, redirigir a sign-in
        console.warn('Error validating session in middleware:', error);
        return NextResponse.redirect(new URL('/sign-in', request.url));
    }

    // Añadir headers de rate limit
    const response = NextResponse.next();
    response.headers.set('X-RateLimit-Limit', RATE_LIMITS.API_ROUTE.limit.toString());
    response.headers.set('X-RateLimit-Remaining', rateLimitResult.remaining.toString());
    response.headers.set('X-RateLimit-Reset', new Date(rateLimitResult.resetAt).toISOString());

    return response;
}

export const config = {
    matcher: [
        '/((?!api|_next/static|_next/image|favicon.ico|sign-in|sign-up|assets).*)',
    ],
};
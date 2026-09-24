'use server';

import { revalidatePath } from 'next/cache';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchRequest, jsonBody } from '@/lib/research/client';
import { cachedFetch } from '@/lib/cache/memoryTTL';
import { requestCache } from '@/lib/cache/requestCache';
import { classifyError, getFriendlyErrorMessage, type ErrorCause } from '@/lib/types/errors';

// Helper para obtener userId (researchRequest añade la identidad firmada
// vía researchIdentityHeaders usando el usuario autenticado).
async function getUserId(): Promise<string> {
    return (await requireAuthenticatedUser()).id;
}

/** Resultado de una mutación de watchlist (serializable a cliente). */
export interface WatchlistMutationResult {
    success: boolean;
    /** Causa del fallo para decidir el toast (offline → Reintentar, duplicate...) */
    code?: ErrorCause;
    message?: string;
}

function failure(error: unknown): WatchlistMutationResult {
    return {
        success: false,
        code: classifyError(error),
        message: getFriendlyErrorMessage(error, { duplicateMessage: 'Ya sigues este ticker.' }),
    };
}

/** Entrada devuelta por GET /api/watchlist del backend research. */
interface WatchlistEntry {
    symbol: string;
    company?: string | null;
    created_at?: string;
}

// Obtener watchlist del usuario actual desde el backend research (/api/watchlist)
export async function getWatchlist(): Promise<{ symbol: string; addedAt: Date }[]> {
    try {
        const userId = await getUserId();
        const items = await cachedFetch(
            `watchlist:${userId}`,
            () => researchRequest<WatchlistEntry[]>('/api/watchlist'),
            15,
        );
        if (!Array.isArray(items)) return [];
        return items.map((item) => ({
            symbol: item.symbol,
            addedAt: item.created_at ? new Date(item.created_at) : new Date()
        }));
    } catch (error) {
        // Backend no disponible / ruta aún no creada: degrada sin romper.
        console.error('getWatchlist error:', error);
        return [];
    }
}

// Añadir a watchlist
export async function addToWatchlist(symbol: string, company?: string): Promise<WatchlistMutationResult> {
    try {
        const userId = await getUserId();
        await researchRequest('/api/watchlist', {
            method: 'POST',
            body: jsonBody({
                symbol: symbol.toUpperCase(),
                ...(company ? { company } : {})
            })
        });
        requestCache.invalidate(`watchlist:${userId}`);
        revalidatePath('/watchlist');
        return { success: true };
    } catch (error) {
        console.error('addToWatchlist error:', error);
        return failure(error);
    }
}

// Eliminar de watchlist
export async function removeFromWatchlist(symbol: string): Promise<WatchlistMutationResult> {
    try {
        const userId = await getUserId();
        await researchRequest(`/api/watchlist/${encodeURIComponent(symbol)}`, {
            method: 'DELETE'
        });
        requestCache.invalidate(`watchlist:${userId}`);
        revalidatePath('/watchlist');
        return { success: true };
    } catch (error) {
        console.error('removeFromWatchlist error:', error);
        return failure(error);
    }
}
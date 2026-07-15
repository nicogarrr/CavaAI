'use server';

import { connectToDatabase } from '@/database/mongoose';
import { Watchlist } from '@/database/models/watchlist.model';
import { revalidatePath } from 'next/cache';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';

// Helper para obtener userId
async function getUserId(): Promise<string> {
    return (await requireAuthenticatedUser()).id;
}

// Obtener watchlist del usuario actual
export async function getWatchlist(): Promise<{ symbol: string; addedAt: Date }[]> {
    try {
        const userId = await getUserId();
        await connectToDatabase();
        const items = await Watchlist.find({ userId }).sort({ createdAt: -1 }).lean();
        return items.map((item: any) => ({
            symbol: item.symbol,
            addedAt: item.createdAt || new Date()
        }));
    } catch (error) {
        console.error('getWatchlist error:', error);
        return [];
    }
}

// Añadir a watchlist
// Añadir a watchlist
export async function addToWatchlist(symbol: string, company?: string): Promise<{ success: boolean }> {
    try {
        const userId = await getUserId();
        await connectToDatabase();

        // Verificar si ya existe
        const existing = await Watchlist.findOne({ userId, symbol: symbol.toUpperCase() });
        if (existing) {
            return { success: true }; // Ya existe
        }

        const companyName = company || symbol; // Fallback

        await Watchlist.create({
            userId,
            symbol: symbol.toUpperCase(),
            company: companyName
        });
        revalidatePath('/watchlist');
        return { success: true };
    } catch (error) {
        console.error('addToWatchlist error:', error);
        return { success: false };
    }
}

// Eliminar de watchlist
export async function removeFromWatchlist(symbol: string): Promise<{ success: boolean }> {
    try {
        const userId = await getUserId();
        await connectToDatabase();
        await Watchlist.deleteOne({ userId, symbol: symbol.toUpperCase() });
        revalidatePath('/watchlist');
        return { success: true };
    } catch (error) {
        console.error('removeFromWatchlist error:', error);
        return { success: false };
    }
}

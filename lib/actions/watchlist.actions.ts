'use server';

import { connectToDatabase } from '@/database/mongoose';
import { Watchlist } from '@/database/models/watchlist.model';
import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';
import { revalidatePath } from 'next/cache';

// Helper para obtener userId
async function getUserId(): Promise<string | null> {
    try {
        const auth = await getAuth();
        if (!auth) return process.env.NODE_ENV === 'development' ? 'dev-user-123' : null;
        const session = await auth.api.getSession({ headers: await headers() });
        if (!session?.user?.id) {
            return process.env.NODE_ENV === 'development' ? 'dev-user-123' : null;
        }
        return session.user.id;
    } catch {
        return process.env.NODE_ENV === 'development' ? 'dev-user-123' : null;
    }
}

export async function getWatchlistSymbolsByEmail(email: string): Promise<string[]> {
    if (!email) return [];

    try {
        const mongoose = await connectToDatabase();
        const db = mongoose.connection.db;
        if (!db) throw new Error('MongoDB connection not found');

        // Better Auth stores users in the "user" collection
        const user = await db.collection('user').findOne<{ _id?: unknown; id?: string; email?: string }>({ email });

        if (!user) return [];

        const userId = (user.id as string) || String(user._id || '');
        if (!userId) return [];

        const items = await Watchlist.find({ userId }, { symbol: 1 }).lean();
        return items.map((i) => String(i.symbol));
    } catch (err) {
        console.error('getWatchlistSymbolsByEmail error:', err);
        return [];
    }
}

// Obtener watchlist del usuario actual
export async function getWatchlist(): Promise<{ symbol: string; addedAt: Date }[]> {
    try {
        const userId = await getUserId();
        if (!userId) return [];

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
export async function addToWatchlist(symbol: string): Promise<{ success: boolean }> {
    try {
        const userId = await getUserId();
        if (!userId) return { success: false };

        await connectToDatabase();

        // Verificar si ya existe
        const existing = await Watchlist.findOne({ userId, symbol: symbol.toUpperCase() });
        if (existing) {
            return { success: true }; // Ya existe
        }

        await Watchlist.create({ userId, symbol: symbol.toUpperCase() });
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
        if (!userId) return { success: false };

        await connectToDatabase();
        await Watchlist.deleteOne({ userId, symbol: symbol.toUpperCase() });
        revalidatePath('/watchlist');
        return { success: true };
    } catch (error) {
        console.error('removeFromWatchlist error:', error);
        return { success: false };
    }
}
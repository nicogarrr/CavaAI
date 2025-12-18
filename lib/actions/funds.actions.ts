'use server';

import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';

const API_URL = 'http://127.0.0.1:8001';

export async function getFundRanking(category: string, limit: number = 10) {
    try {
        const auth = await getAuth();
        const session = await auth.api.getSession({ headers: await headers() });

        // Optional: Require auth to fetch
        // if (!session) return { success: false, error: "Unauthorized" };

        const res = await fetch(`${API_URL}/funds/ranking?category=${encodeURIComponent(category)}&limit=${limit}`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
            cache: 'no-store' // Always fresh data
        });

        if (!res.ok) {
            throw new Error(`API Error: ${res.statusText}`);
        }

        const data = await res.json();

        if (data.success) {
            return { success: true, data: data.data };
        } else {
            return { success: false, error: data.error };
        }

    } catch (error: any) {
        console.error("Fund Ranking Error:", error);
        return { success: false, error: "Error de conexión con el motor de datos." };
    }
}

export async function getFundCategories() {
    try {
        const res = await fetch(`${API_URL}/funds/categories`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
            cache: 'no-store'
        });

        if (!res.ok) {
            throw new Error(`API Error: ${res.statusText}`);
        }

        const data = await res.json();

        if (data.success) {
            return { success: true, data: data.data };
        } else {
            return { success: false, error: data.error };
        }

    } catch (error: any) {
        console.error("Fund Categories Error:", error);
        return { success: false, error: "Error de conexión." };
    }
}

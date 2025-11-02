'use server';

import { connectToDatabase } from '@/database/mongoose';
import { AlertModel, type Alert } from '@/database/models/alert.model';
import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';

export interface CreateAlertInput {
    symbol: string;
    type: 'price_above' | 'price_below' | 'price_change' | 'news' | 'earnings';
    condition: {
        operator: '>' | '<' | '>=' | '<=' | '==';
        value: number | string;
    };
}

export async function createAlert(input: CreateAlertInput): Promise<Alert | null> {
    try {
        const auth = await getAuth();
        const session = await auth.api.getSession({ headers: await headers() });
        if (!session?.user?.id) throw new Error('Usuario no autenticado');

        await connectToDatabase();

        const alert = await AlertModel.create({
            userId: session.user.id,
            symbol: input.symbol.toUpperCase(),
            type: input.type,
            condition: input.condition,
            isActive: true,
        });

        return JSON.parse(JSON.stringify(alert));
    } catch (error) {
        console.error('Error creating alert:', error);
        throw error;
    }
}

export async function getUserAlerts(): Promise<Alert[]> {
    try {
        const auth = await getAuth();
        const session = await auth.api.getSession({ headers: await headers() });
        if (!session?.user?.id) throw new Error('Usuario no autenticado');

        await connectToDatabase();

        const alerts = await AlertModel.find({ 
            userId: session.user.id,
            isActive: true 
        })
        .sort({ createdAt: -1 })
        .lean();

        return JSON.parse(JSON.stringify(alerts));
    } catch (error) {
        console.error('Error getting user alerts:', error);
        throw error;
    }
}

export async function deleteAlert(alertId: string): Promise<void> {
    try {
        const auth = await getAuth();
        const session = await auth.api.getSession({ headers: await headers() });
        if (!session?.user?.id) throw new Error('Usuario no autenticado');

        await connectToDatabase();

        await AlertModel.findOneAndUpdate(
            { _id: alertId, userId: session.user.id },
            { isActive: false }
        );
    } catch (error) {
        console.error('Error deleting alert:', error);
        throw error;
    }
}


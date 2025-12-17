'use server';

import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';
import mongoose from 'mongoose';
import { ThesisChecklist, CHECKLIST_QUESTIONS, IThesisChecklist } from '@/database/models/checklist.model';

// Conectar a MongoDB si no está conectado
async function connectDB() {
    if (mongoose.connection.readyState >= 1) return;
    const uri = process.env.MONGODB_URI;
    if (!uri) throw new Error('MONGODB_URI not configured');
    await mongoose.connect(uri);
}

// Obtener usuario autenticado
async function getAuthenticatedUser() {
    const auth = await getAuth();
    if (!auth) throw new Error('Auth not initialized');
    const session = await auth.api.getSession({ headers: await headers() });
    if (!session?.user) throw new Error('User not authenticated');
    return session.user;
}

// Obtener todas las preguntas del checklist
export async function getChecklistQuestions() {
    return CHECKLIST_QUESTIONS;
}

// Obtener o crear checklist para un símbolo
export async function getOrCreateChecklist(symbol: string, companyName: string): Promise<IThesisChecklist | null> {
    try {
        const user = await getAuthenticatedUser();
        await connectDB();

        let checklist = await ThesisChecklist.findOne({
            userId: user.id,
            symbol: symbol.toUpperCase()
        });

        if (!checklist) {
            // Crear checklist vacío con todas las preguntas
            const emptyAnswers = CHECKLIST_QUESTIONS.map(q => ({
                questionId: q.id,
                answer: 'unknown' as const,
                notes: ''
            }));

            checklist = new ThesisChecklist({
                userId: user.id,
                symbol: symbol.toUpperCase(),
                companyName,
                answers: emptyAnswers,
                status: 'observando'
            });

            await checklist.save();
        }

        return JSON.parse(JSON.stringify(checklist));
    } catch (error) {
        console.error('Error getting checklist:', error);
        return null;
    }
}

// Guardar respuestas del checklist
export async function saveChecklistAnswers(
    symbol: string,
    answers: { questionId: string; answer: 'yes' | 'no' | 'maybe' | 'unknown'; notes?: string }[]
): Promise<{ success: boolean; checklist?: IThesisChecklist; error?: string }> {
    try {
        const user = await getAuthenticatedUser();
        await connectDB();

        const checklist = await ThesisChecklist.findOne({
            userId: user.id,
            symbol: symbol.toUpperCase()
        });

        if (!checklist) {
            return { success: false, error: 'Checklist not found' };
        }

        checklist.answers = answers;
        checklist.calculateScore();
        await checklist.save();

        return { success: true, checklist: JSON.parse(JSON.stringify(checklist)) };
    } catch (error: any) {
        console.error('Error saving checklist:', error);
        return { success: false, error: error.message };
    }
}

// Actualizar estado del checklist
export async function updateChecklistStatus(
    symbol: string,
    status: 'observando' | 'en_punto' | 'invertido' | 'descartado'
): Promise<{ success: boolean; error?: string }> {
    try {
        const user = await getAuthenticatedUser();
        await connectDB();

        await ThesisChecklist.findOneAndUpdate(
            { userId: user.id, symbol: symbol.toUpperCase() },
            { status },
            { new: true }
        );

        return { success: true };
    } catch (error: any) {
        console.error('Error updating status:', error);
        return { success: false, error: error.message };
    }
}

// Guardar tesis de inversión
export async function saveThesis(
    symbol: string,
    thesis: string
): Promise<{ success: boolean; error?: string }> {
    try {
        const user = await getAuthenticatedUser();
        await connectDB();

        await ThesisChecklist.findOneAndUpdate(
            { userId: user.id, symbol: symbol.toUpperCase() },
            { thesis },
            { new: true }
        );

        return { success: true };
    } catch (error: any) {
        console.error('Error saving thesis:', error);
        return { success: false, error: error.message };
    }
}

// Obtener todos los checklists del usuario
export async function getUserChecklists(): Promise<IThesisChecklist[]> {
    try {
        const user = await getAuthenticatedUser();
        await connectDB();

        const checklists = await ThesisChecklist.find({ userId: user.id })
            .sort({ updatedAt: -1 })
            .lean();

        return JSON.parse(JSON.stringify(checklists));
    } catch (error) {
        console.error('Error getting user checklists:', error);
        return [];
    }
}

// Obtener checklists por estado
export async function getChecklistsByStatus(
    status: 'observando' | 'en_punto' | 'invertido' | 'descartado'
): Promise<IThesisChecklist[]> {
    try {
        const user = await getAuthenticatedUser();
        await connectDB();

        const checklists = await ThesisChecklist.find({ userId: user.id, status })
            .sort({ updatedAt: -1 })
            .lean();

        return JSON.parse(JSON.stringify(checklists));
    } catch (error) {
        console.error('Error getting checklists by status:', error);
        return [];
    }
}

// Eliminar checklist
export async function deleteChecklist(symbol: string): Promise<{ success: boolean; error?: string }> {
    try {
        const user = await getAuthenticatedUser();
        await connectDB();

        await ThesisChecklist.findOneAndDelete({
            userId: user.id,
            symbol: symbol.toUpperCase()
        });

        return { success: true };
    } catch (error: any) {
        console.error('Error deleting checklist:', error);
        return { success: false, error: error.message };
    }
}

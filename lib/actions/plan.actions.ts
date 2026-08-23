'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchRequest } from '@/lib/research/client';

export type PlanRecord = Record<string, unknown>;

/** GET /api/plan — plan de inversión a largo plazo */
export async function getPlan(): Promise<PlanRecord> {
    await requireAuthenticatedUser();
    return researchRequest<PlanRecord>('/api/plan');
}

/** GET /api/plan/contributions — historial de aportaciones */
export async function getPlanContributions(): Promise<PlanRecord[]> {
    await requireAuthenticatedUser();
    return researchRequest<PlanRecord[]>('/api/plan/contributions');
}

/** GET /api/plan/drift — análisis de desviación respecto al objetivo */
export async function getPlanDrift(): Promise<PlanRecord> {
    await requireAuthenticatedUser();
    return researchRequest<PlanRecord>('/api/plan/drift');
}
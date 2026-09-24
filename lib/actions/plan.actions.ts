'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchRequest } from '@/lib/research/client';

export type PlanRecord = Record<string, unknown>;

/** El backend responde {"plan_exists": false} cuando no hay plan: se
 *  normaliza a null para que la UI muestre su estado vacío honesto en
 *  lugar de pintar el stub crudo ("PLAN_EXISTS No"). */
function nullIfPlanStub(record: PlanRecord | null): PlanRecord | null {
    if (record && record.plan_exists === false) return null;
    return record;
}

/** GET /api/plan — plan de inversión a largo plazo */
export async function getPlan(): Promise<PlanRecord | null> {
    await requireAuthenticatedUser();
    return nullIfPlanStub(await researchRequest<PlanRecord>('/api/plan'));
}

/** GET /api/plan/contributions — historial de aportaciones */
export async function getPlanContributions(): Promise<PlanRecord[]> {
    await requireAuthenticatedUser();
    return researchRequest<PlanRecord[]>('/api/plan/contributions');
}

/** GET /api/plan/drift — análisis de desviación respecto al objetivo */
export async function getPlanDrift(): Promise<PlanRecord | null> {
    await requireAuthenticatedUser();
    return nullIfPlanStub(await researchRequest<PlanRecord>('/api/plan/drift'));
}
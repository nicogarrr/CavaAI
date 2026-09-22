'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchRequest } from '@/lib/research/client';

export interface ThesisJobPhase {
    name: string;
    status: string;
    started_at?: string | null;
    finished_at?: string | null;
}

export interface ThesisJobStatus {
    id: number;
    status: 'queued' | 'running' | 'succeeded' | 'failed' | string;
    ticker: string;
    phases: ThesisJobPhase[];
    current_phase?: string | null;
    result?: { thesis_version_id?: number; version?: number; status?: string } | null;
    error_class?: string | null;
    error_message?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
}

/** POST /api/thesis/generate-async — encola generación en segundo plano (202). */
export async function startThesisJob(ticker: string, force = true): Promise<ThesisJobStatus> {
    await requireAuthenticatedUser();
    return researchRequest<ThesisJobStatus>('/api/thesis/generate-async', {
        method: 'POST',
        body: JSON.stringify({ ticker: ticker.toUpperCase(), force_new_version: force }),
    });
}

/** GET /api/thesis/jobs/{id} — estado real del job (fases reales, sin ETAs). */
export async function getThesisJobStatus(runId: number): Promise<ThesisJobStatus> {
    await requireAuthenticatedUser();
    return researchRequest<ThesisJobStatus>(`/api/thesis/jobs/${runId}`);
}

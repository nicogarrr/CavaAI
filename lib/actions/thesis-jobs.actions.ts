'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchRequest } from '@/lib/research/client';
import { assertPositiveInt } from '@/lib/validation/pathParams';

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

/** POST /api/thesis/generate-async — encola generación en segundo plano (202).
 *  `requestId` identifica el click del usuario: sin él el backend replaya el
 *  último run exitoso y nunca se regeneraría. */
export async function startThesisJob(
    ticker: string,
    force = true,
    requestId?: string,
): Promise<ThesisJobStatus> {
    await requireAuthenticatedUser();
    return researchRequest<ThesisJobStatus>('/api/thesis/generate-async', {
        method: 'POST',
        body: JSON.stringify({
            ticker: ticker.toUpperCase(),
            force_new_version: force,
            ...(requestId ? { request_id: requestId } : {}),
        }),
    });
}

/** GET /api/thesis/jobs/{id} — estado real del job (fases reales, sin ETAs). */
export async function getThesisJobStatus(runId: number): Promise<ThesisJobStatus> {
    await requireAuthenticatedUser();
    return researchRequest<ThesisJobStatus>(`/api/thesis/jobs/${assertPositiveInt(runId, 'runId')}`);
}

export interface ThesisDebateResult {
    ticker: string;
    thesis_version_id?: number;
    persisted?: boolean;
    bull_case: string;
    bear_case: string;
    verdict: 'bullish' | 'bearish' | 'neutral' | string;
    verdict_rationale: string;
    llm_calls: number;
    degraded: boolean;
    model: string | null;
}

/** POST /api/thesis/{ticker}/debate — debate bull/bear (degrada a determinista). */
export async function runThesisDebate(ticker: string): Promise<ThesisDebateResult> {
    await requireAuthenticatedUser();
    const clean = ticker.trim().toUpperCase();
    if (!/^[A-Z0-9.\-]{1,20}$/.test(clean)) throw new Error('Ticker no válido');
    return researchRequest<ThesisDebateResult>(`/api/thesis/${encodeURIComponent(clean)}/debate`, {
        method: 'POST',
    });
}

export interface ThesisApproval {
    ticker: string;
    thesis_version_id: number;
    version: number;
    status: string;
    decision: 'approved' | 'rejected';
    actor: string;
    approved_at: string;
    telegram_auto_approval: string;
}

/**
 * POST /api/thesis/{ticker}/approve — aprobacion manual de la ultima tesis.
 * La aprobacion automatica por Telegram queda como futura (el endpoint lo
 * declara en `telegram_auto_approval: "future"`).
 */
export async function approveThesis(
    ticker: string,
    decision: 'approved' | 'rejected',
    actor = 'user',
): Promise<ThesisApproval> {
    await requireAuthenticatedUser();
    const clean = ticker.trim().toUpperCase();
    if (!/^[A-Z0-9.\-]{1,20}$/.test(clean)) throw new Error('Ticker no válido');
    if (decision !== 'approved' && decision !== 'rejected') throw new Error('Decisión no válida');
    return researchRequest<ThesisApproval>(`/api/thesis/${encodeURIComponent(clean)}/approve`, {
        method: 'POST',
        body: JSON.stringify({ decision, actor: actor.slice(0, 160) || 'user' }),
    });
}

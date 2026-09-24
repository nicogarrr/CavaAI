'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { jsonBody, researchRequest } from '@/lib/research/client';
import { AuthorizationError, ValidationError } from '@/lib/types/errors';

type ResearchChatResponse = {
    answer: string;
    blocked: boolean;
    proposed_actions: string[];
    sources: Array<{
        type: string;
        id: number | string | null;
        title: string;
        document_id?: number | null;
        page_number?: number | null;
        chunk_index?: number | null;
        source_type?: string | null;
        [key: string]: unknown;
    }>;
};

import { toChatCitations } from '@/lib/chat/citations';

export async function chatWithPortfolio(query: string, userId: string) {
    const user = await requireAuthenticatedUser();
    if (userId !== user.id) {
        throw new AuthorizationError('Cannot access another user portfolio');
    }
    const question = query.trim();
    if (question.length < 3) {
        throw new ValidationError('Escribe una pregunta de al menos 3 caracteres', 'query');
    }
    const response = await researchRequest<ResearchChatResponse>('/api/chat', {
        method: 'POST',
        body: jsonBody({ question, scope: 'portfolio', ticker: null }),
    });
    return {
        success: !response.blocked,
        message: response.answer,
        proposedActions: response.proposed_actions,
        citations: toChatCitations(response.sources),
    };
}

/** Chat de empresa con citas trazables (scope company + debate opcional). */
export async function chatWithCompany(
    ticker: string,
    query: string,
    options?: { enableDebate?: boolean },
) {
    await requireAuthenticatedUser();
    const clean = ticker.trim().toUpperCase();
    if (!/^[A-Z0-9.\-]{1,20}$/.test(clean)) {
        throw new ValidationError('A valid ticker is required', 'ticker');
    }
    const question = query.trim();
    if (question.length < 3) {
        throw new ValidationError('Escribe una pregunta de al menos 3 caracteres', 'query');
    }
    const response = await researchRequest<ResearchChatResponse>('/api/chat', {
        method: 'POST',
        body: jsonBody({
            question,
            scope: 'company',
            ticker: clean,
            enable_debate: options?.enableDebate ?? false,
        }),
    });
    return {
        success: !response.blocked,
        message: response.answer,
        proposedActions: response.proposed_actions,
        citations: toChatCitations(response.sources),
        sources: response.sources ?? [],
    };
}

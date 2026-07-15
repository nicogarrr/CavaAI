'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { jsonBody, researchRequest } from '@/lib/research/client';
import { AuthorizationError, ValidationError } from '@/lib/types/errors';

type ResearchChatResponse = {
    answer: string;
    blocked: boolean;
    proposed_actions: string[];
};

export async function chatWithPortfolio(query: string, userId: string) {
    const user = await requireAuthenticatedUser();
    if (userId !== user.id) {
        throw new AuthorizationError('Cannot access another user portfolio');
    }
    const question = query.trim();
    if (question.length < 3) {
        throw new ValidationError('Write a question with at least 3 characters', 'query');
    }
    const response = await researchRequest<ResearchChatResponse>('/api/chat', {
        method: 'POST',
        body: jsonBody({ question, scope: 'portfolio', ticker: null }),
    });
    return {
        success: !response.blocked,
        message: response.answer,
        proposedActions: response.proposed_actions,
    };
}

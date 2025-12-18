'use server';

import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';
import { GoogleGenerativeAI } from '@google/generative-ai';
import { getPortfolioSummary } from './portfolio.actions';
import { getRAGContext } from './ai.actions'; // Reuse existing RAG function!

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY!);

export async function chatWithPortfolio(query: string, userId: string) {
    try {
        // 1. Get Portfolio Context
        const summary = await getPortfolioSummary(userId);

        // 2. Get RAG Context (Knowledge Base) based on query
        // e.g. if user asks "Why did I buy AMZN?", we search for "Amazon thesis"
        // We pass the query as the "symbol" parameter effectively, or we need to update getRAGContext to be more flexible. 
        // For now, let's just pass the query as the first arg and empty string as second. 
        // Ideally getRAGContext should support a generic query mode.
        const ragContext = await getRAGContext(query, '');

        // 3. Construct Prompt
        const model = genAI.getGenerativeModel({ model: 'gemini-3-flash-preview' });

        const prompt = `
    You are an intelligent financial assistant named "CavaAI" integrated into the user's portfolio dashboard.
    
    USER QUESTION: "${query}"

    ---
    PORTFOLIO CONTEXT:
    Total Value: $${summary.totalValue}
    Total Gain: ${summary.totalGainPercent.toFixed(2)}%
    Holdings: ${summary.holdings.map((h: any) => `${h.symbol} (${h.shares} sh, $${h.value.toFixed(0)}, ${h.gainPercent.toFixed(1)}%)`).join(', ')}
    ---
    KNOWLEDGE BASE (User's Notes/Strategy):
    ${ragContext ? ragContext : "No relevant strategy documents found."}
    ---

    INSTRUCTIONS:
    1. Answer the user's question concisely.
    2. Use the Portfolio Context to give specific numbers.
    3. Use the Knowledge Base to explain *why* (theses, rules).
    4. If the question is about real-time news (e.g. "Why is X down today?"), admit you don't have live news unless it's in the RAG context (which it likely isn't), but offer a general financial explanation or suggest checking the News section.
    5. Be helpful, professional, and slightly "Value Investing" biased.
    `;

        const result = await model.generateContent(prompt);
        const response = result.response.text();

        return { success: true, message: response };

    } catch (error: any) {
        console.error("Chat Action Error Details:", {
            message: error.message,
            stack: error.stack,
            cause: error.cause,
            apiKeyPresent: !!process.env.GEMINI_API_KEY
        });
        return { success: false, message: `Error interno: ${error.message}` };
    }
}

'use server';

import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';
import { GoogleGenerativeAI } from '@google/generative-ai';
import { getPortfolioSummary } from './portfolio.actions';
import { getRAGContext } from './ai.actions'; // Reuse existing RAG function!

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY!);

export async function chatWithPortfolio(query: string, userId: string) {
    try {
        console.log("👉 [CHAT DEBUG] STEP 1: Getting Portfolio Summary...");
        // 1. Get Portfolio Context
        const summary = await getPortfolioSummary(userId);
        console.log("👉 [CHAT DEBUG] Portfolio Summary OK. Total Value:", summary.totalValue);

        // 2. Get RAG Context (Knowledge Base) based on query
        console.log("👉 [CHAT DEBUG] STEP 2: Getting RAG Context for:", query);
        const ragContext = await getRAGContext(query, '');
        console.log("👉 [CHAT DEBUG] RAG Context Length:", ragContext.length);

        // 3. Construct Prompt
        const model = genAI.getGenerativeModel({ model: 'gemini-3-pro-preview' });

        const prompt = `
    Eres "CavaAI", un analista estratégico personal de inversiones de alto nivel (Nivel Institucional/Warren AI killer), integrado en la cartera del usuario.
    
    PREGUNTA DEL USUARIO: "${query}"

    ---
    CONTEXTO DE LA CARTERA (DATOS EN TIEMPO REAL):
    Valor Total: $${summary.totalValue?.toLocaleString() || '0'}
    Ganancia Total: $${summary.totalGain?.toLocaleString() || '0'} (${(summary.totalGainPercent || 0).toFixed(2)}%)
    Posiciones Individuales:
    ${summary.holdings.map((h: any) => `- ${h.symbol}: $${(h.value || 0).toFixed(0)} (Peso: ${((h.value / (summary.totalValue || 1)) * 100).toFixed(1)}%) | Rendimiento: ${(h.gainPercent || 0).toFixed(2)}% | Precio Promedio: $${(h.averagePrice || 0).toFixed(2)} | Precio Actual: $${(h.price || 0).toFixed(2)}`).join('\n    ')}
    ---
    BASE DE CONOCIMIENTO (TESIS Y REGLAS DEL USUARIO):
    ${ragContext ? ragContext : "No se encontraron documentos de estrategia específicos para esta consulta, usa principios generales de Value Investing (Margin of Safety, Moat, Management)."}
    ---

    INSTRUCCIONES DE RESPUESTA (MODO SUPERIOR A WARREN AI):
    1. **NO repitas la pregunta**.
    2. **Responde SIEMPRE en Español.**
    3. **SI TE PIDEN ANALIZAR UNA EMPRESA**, usa OBLIGATORIAMENTE esta estructura (Estilo "Warren AI Plus"):
       - **📊 1. Situación en Cartera**: Peso exacto, G/P y precio de entrada vs actual.
       - **🧠 2. Tesis & Estrategia (RAG)**: ¿Por qué la tienes? (Cita tu base de conocimiento).
       - **⚖️ 3. SWOT Analysis (FODA)**:
         - *Fortalezas*: (Moat, Márgenes, Marca)
         - *Debilidades*: (Deuda, Competencia)
         - *Oportunidades*: (Nuevos mercados, Bajada tipos)
         - *Amenazas*: (Regulación, Macro)
       - **🐂 Vs 🐻 Bull/Bear Case**:
         - *Bull Case*: ¿Qué tiene que pasar para que suba un 50%?
         - *Bear Case*: ¿Cuál es el riesgo catastrófico?
       - **🎯 4. Conclusión/Acción**: Mantener, Acumular o Vender.
    
    4. Si es una pregunta general ("¿Cuánto cobro en dividendos?"), sé directo y breve.
    5. Mantén un tono de "Socio Senior": calmado, basado en datos y enfocado en el largo plazo.
    `;


        // ... Prompt construction ...


        // 4. Robust Generation Strategy (Multi-Tier Fallback)
        const modelsToTry = [
            'gemini-3-flash-preview', // 1. User Preference (Pro)
            'gemini-3-pro-preview',     // 2. User Preference (Pro)
        ];

        let lastError;

        for (const modelName of modelsToTry) {
            try {
                console.log(`🧠 Attempting chat with model: ${modelName}...`);
                const modelInstance = genAI.getGenerativeModel({ model: modelName });
                const result = await modelInstance.generateContent(prompt);
                const response = result.response.text();

                console.log(`✅ Success with ${modelName}`);
                return { success: true, message: response };

            } catch (error: any) {
                console.warn(`⚠️ Failed with ${modelName}:`, error.message);
                lastError = error;
                // Continue to next model
            }
        }

        // If all fail
        throw lastError || new Error("All models failed to generate response.");

    } catch (error: any) {
        console.error("Chat Action Fatal Error (All Models Failed):", {
            message: error.message,
            apiKeyPresent: !!process.env.GEMINI_API_KEY
        });
        return { success: false, message: `Error del sistema: Todos los modelos de IA están ocupados o no disponibles. Inténtalo de nuevo. (${error.message})` };
    }
}

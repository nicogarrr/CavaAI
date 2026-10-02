/**
 * Sanea y valida la salida del debate bull/bear (texto generado por un LLM).
 * Nunca se renderiza texto del modelo sin pasar por aqui: se eliminan
 * caracteres de control y escrituras ajenas al espanol/ingles (CJK, etc.),
 * se acota la longitud y se rechaza cualquier forma inesperada.
 */
export interface SanitizedDebate {
    ticker: string;
    thesis_version_id?: number;
    persisted?: boolean;
    bull_case: string;
    bear_case: string;
    verdict: 'bullish' | 'bearish' | 'neutral';
    verdict_rationale: string;
    llm_calls: number;
    degraded: boolean;
    model: string | null;
}

const MAX_TEXT = 6000;
// Control (salvo \n \t), CJK, hangul, kana, fullwidth, zero-width y bidi.
const FORBIDDEN =
    /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F\u200B-\u200F\u202A-\u202E\u2060\u3000-\u303F\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF\uFF00-\uFFEF]/g;

export function sanitizeLlmText(value: unknown, max = MAX_TEXT): string {
    if (typeof value !== 'string') return '';
    return value
        .replace(FORBIDDEN, '')
        .replace(/[ \t]{2,}/g, ' ')
        .replace(/\n{3,}/g, '\n\n')
        .trim()
        .slice(0, max);
}

export function sanitizeDebate(raw: unknown): SanitizedDebate | null {
    if (!raw || typeof raw !== 'object') return null;
    const r = raw as Record<string, unknown>;
    const bull = sanitizeLlmText(r.bull_case);
    const bear = sanitizeLlmText(r.bear_case);
    const rationale = sanitizeLlmText(r.verdict_rationale);
    const verdict = r.verdict === 'bullish' || r.verdict === 'bearish' ? r.verdict : 'neutral';
    if (!bull && !bear && !rationale) return null;
    const calls = typeof r.llm_calls === 'number' && Number.isFinite(r.llm_calls) ? Math.max(0, Math.floor(r.llm_calls)) : 0;
    return {
        ticker: sanitizeLlmText(r.ticker, 20),
        thesis_version_id: typeof r.thesis_version_id === 'number' ? r.thesis_version_id : undefined,
        persisted: typeof r.persisted === 'boolean' ? r.persisted : undefined,
        bull_case: bull,
        bear_case: bear,
        verdict,
        verdict_rationale: rationale,
        llm_calls: calls,
        degraded: r.degraded === true,
        model: typeof r.model === 'string' ? sanitizeLlmText(r.model, 80) || null : null,
    };
}

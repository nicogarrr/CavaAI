export const DEFAULT_GEMINI_MODEL = 'gemini-3.5-flash';
export const DEFAULT_GEMINI_CHEAP_MODEL = 'gemini-2.5-flash-lite';
export const DEFAULT_GEMINI_DEEP_MODEL = 'gemini-3.5-flash';

export function getDefaultGeminiModel(): string {
  return process.env.GEMINI_MODEL || DEFAULT_GEMINI_MODEL;
}

export function getCheapGeminiModel(): string {
  return process.env.GEMINI_CHEAP_MODEL || DEFAULT_GEMINI_CHEAP_MODEL;
}

export function getDeepGeminiModel(): string {
  return process.env.GEMINI_DEEP_MODEL || process.env.GEMINI_MODEL || DEFAULT_GEMINI_DEEP_MODEL;
}

export function getGeminiModelFallbacks(): string[] {
  return [
    getDefaultGeminiModel(),
    getDeepGeminiModel(),
    getCheapGeminiModel(),
  ].filter((model, index, models) => model && models.indexOf(model) === index);
}

export function getGeminiGenerateContentEndpoint(model: string, apiKey: string): string {
  return `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
}

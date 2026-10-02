import type { E2EConfig } from 'e2e';
import { web } from '@e2e-dev/web';
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

// OpenCode Zen (modelo gratuito). La clave llega por entorno, nunca en el repo.
// Zen exige la cabecera de sesion y un User-Agent distinto del por defecto
// (python-urllib/undici genericos reciben 403 1010 de Cloudflare).
const zen = createOpenAICompatible({
  name: 'opencode-zen',
  baseURL: process.env.ZEN_BASE_URL ?? 'https://opencode.ai/zen/v1',
  apiKey: process.env.OPENCODE_API_KEY,
  headers: {
    'x-opencode-session': process.env.ZEN_SESSION_ID ?? 'cavaai-e2e-readonly',
    'User-Agent': 'curl/8.5.0',
  },
});

export default {
  agents: { default: { model: zen.chatModel(process.env.ZEN_MODEL ?? 'space-bunny-free') } },
  targets: [{ engine: web(), app: { url: process.env.E2E_BASE_URL ?? 'https://cavaai.vercel.app' } }],
  workers: 1,
  // Sin trazas ni video: la pasada autenticada usa una sesion real y no debe dejar
  // en artefactos ni la contrasena tecleada ni datos de la cuenta.
  trace: 'off',
  video: 'off',
} satisfies E2EConfig;

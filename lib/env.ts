/**
 * Validación de variables de entorno usando Zod
 * Falla al inicio si faltan variables críticas
 */

import { z } from 'zod';

// Schema para variables de entorno
const envSchema = z.object({
  // Core
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),

  // Database - Requerido en runtime, opcional en build
  MONGODB_URI: z.string().min(1).optional(),

  // Better Auth - Requerido en producción
  BETTER_AUTH_SECRET: z.string().min(32, 'BETTER_AUTH_SECRET debe tener al menos 32 caracteres'),
  BETTER_AUTH_URL: z.string().url().optional(),

  // Finnhub - Opcional (hay fallback)
  FINNHUB_API_KEY: z.string().optional(),
  FINNHUB_BASE_URL: z.string().url().default('https://finnhub.io/api/v1'),

  // FMP - Financial Modeling Prep
  FMP_API_KEY: z.string().optional(),

  // Fuentes alternativas - Opcionales
  TWELVE_DATA_API_KEY: z.string().optional(),
  ALPHA_VANTAGE_API_KEY: z.string().optional(),
  POLYGON_API_KEY: z.string().optional(),
  MARKETSTACK_API_KEY: z.string().optional(),
  NEWSAPI_KEY: z.string().optional(),
  MARKETAUX_API_KEY: z.string().optional(),

  // Inngest AI
  GEMINI_API_KEY: z.string().optional(),

  // Email - Opcional
  NODEMAILER_EMAIL: z.string().email().optional(),
  NODEMAILER_PASSWORD: z.string().optional(),

  // Vercel
  VERCEL_URL: z.string().optional(),
});

// Validar variables de entorno
function validateEnv() {
  const isBuildTime = process.env.NEXT_PHASE === 'phase-production-build' ||
    process.env.NEXT_PHASE === 'phase-development-build';

  // En build time, algunas variables pueden faltar
  if (isBuildTime) {
    const buildSchema = envSchema.partial().extend({
      BETTER_AUTH_SECRET: z.string().min(1).optional(),
    });

    try {
      return buildSchema.parse(process.env);
    } catch (error) {
      if (error instanceof z.ZodError) {
        console.warn('⚠️ Algunas variables de entorno faltan durante el build:', error.errors.map(e => e.path.join('.')).join(', '));
      }
      return buildSchema.parse(process.env);
    }
  }

  // En runtime, validar completamente
  try {
    return envSchema.parse(process.env);
  } catch (error) {
    if (error instanceof z.ZodError) {
      const missingVars = error.errors.map(e => `${e.path.join('.')}: ${e.message}`).join('\n');
      throw new Error(
        `❌ Error de validación de variables de entorno:\n${missingVars}\n\n` +
        `Por favor, revisa tu archivo .env y asegúrate de que todas las variables requeridas estén configuradas.`
      );
    }
    throw error;
  }
}

// Validar y exportar
export const env = validateEnv();

// Validar que BETTER_AUTH_SECRET sea seguro en producción
if (env.NODE_ENV === 'production') {
  if (!env.BETTER_AUTH_SECRET || env.BETTER_AUTH_SECRET.length < 32) {
    throw new Error(
      '❌ BETTER_AUTH_SECRET debe tener al menos 32 caracteres en producción. ' +
      'Genera uno seguro con: openssl rand -base64 32'
    );
  }

  // No permitir valores por defecto inseguros
  const insecureSecrets = ['fallback-secret', 'dummy-secret-for-build', 'your_better_auth_secret'];
  if (insecureSecrets.includes(env.BETTER_AUTH_SECRET)) {
    throw new Error(
      '❌ BETTER_AUTH_SECRET no puede usar valores por defecto inseguros en producción. ' +
      'Por favor, configura un secreto seguro.'
    );
  }
}

// Helper para verificar si una variable está configurada
export function isEnvVarSet(key: keyof typeof env): boolean {
  return env[key] !== undefined && env[key] !== '';
}

// Tipos inferidos del schema
export type Env = z.infer<typeof envSchema>;


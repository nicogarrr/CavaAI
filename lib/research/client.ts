import {
  normalizeResearchBody,
  researchIdentityHeaders,
} from '@/lib/auth/research-identity';
import { AppError, ExternalAPIError } from '@/lib/types/errors';

const BACKEND_URL = process.env.FMP_BACKEND_URL ?? 'http://localhost:8000';

async function responseError(response: Response, path: string): Promise<never> {
  let detail = `${response.status} ${response.statusText}`.trim();
  try {
    const payload = await response.json() as { detail?: string; message?: string };
    detail = payload.detail ?? payload.message ?? detail;
  } catch {
    // Preserve the HTTP status when the backend did not return JSON.
  }
  throw new AppError(detail, 'RESEARCH_API_ERROR', response.status, { path });
}

export async function researchRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const normalized = await normalizeResearchBody(init.body ?? null);
  const identityHeaders = await researchIdentityHeaders({
    method,
    path,
    body: normalized.body ?? null,
  });
  const headers = new Headers(init.headers);
  for (const [key, value] of Object.entries(identityHeaders)) headers.set(key, value);
  if (normalized.contentType && !headers.has('Content-Type')) {
    headers.set('Content-Type', normalized.contentType);
  } else if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}${path}`, {
      ...init,
      body: normalized.body ?? undefined,
      headers,
      cache: init.cache ?? 'no-store',
    });
  } catch (error) {
    throw new ExternalAPIError(
      `Research engine unavailable for ${path}`,
      'research-engine',
      error,
    );
  }

  if (!response.ok) await responseError(response, path);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}

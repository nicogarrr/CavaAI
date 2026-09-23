import 'server-only';

import createClient from 'openapi-fetch';
import type { paths } from '@/lib/research/openapi.generated';
import { researchIdentityHeaders } from '@/lib/auth/research-identity';

const BACKEND_URL = process.env.FMP_BACKEND_URL ?? 'http://localhost:8000';
export function createResearchOpenApiClient() {
  return createClient<paths>({
    baseUrl: BACKEND_URL,
    fetch: async (request: Request) => {
      const url = new URL(request.url);
      const body = request.body ? await request.arrayBuffer() : null;
      const identity = await researchIdentityHeaders({
        method: request.method,
        path: url.pathname,
        body,
      });
      const headers = new Headers(request.headers);
      for (const [key, value] of Object.entries(identity)) headers.set(key, value);
      return fetch(request.url, {
        method: request.method,
        headers,
        body: body ?? undefined,
        cache: 'no-store',
      });
    },
  });
}

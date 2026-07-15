import 'server-only';

import createClient from 'openapi-fetch';
import type { paths } from '@/lib/research/openapi.generated';
import { researchIdentityHeaders } from '@/lib/auth/research-identity';

const BACKEND_URL = process.env.FMP_BACKEND_URL ?? 'http://localhost:8000';

export function createResearchOpenApiClient() {
  return createClient<paths>({
    baseUrl: BACKEND_URL,
    fetch: async (input, init) => {
      const identity = await researchIdentityHeaders();
      const headers = new Headers(init?.headers);
      for (const [key, value] of Object.entries(identity)) headers.set(key, value);
      return fetch(input, { ...init, cache: 'no-store', headers });
    },
  });
}

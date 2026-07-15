import { headers } from 'next/headers';

import { getAuth } from '@/lib/better-auth/auth';
import { AuthenticationError } from '@/lib/types/errors';

export type AuthenticatedUser = {
  id: string;
  email?: string | null;
  name?: string | null;
};

/** Resolve identity server-side; caller-supplied user IDs are never trusted. */
export async function requireAuthenticatedUser(): Promise<AuthenticatedUser> {
  if (process.env.E2E_AUTH_BYPASS === '1' && process.env.NODE_ENV !== 'production') {
    return { id: 'e2e-browser-user', email: 'browser@cavaai.test', name: 'Browser Analyst' };
  }
  const auth = await getAuth();
  const session = await auth.api.getSession({ headers: await headers() });
  const user = session?.user;
  if (!user?.id) {
    throw new AuthenticationError('User not authenticated');
  }
  return { id: user.id, email: user.email, name: user.name };
}

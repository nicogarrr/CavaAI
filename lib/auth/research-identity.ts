import { createHmac } from 'node:crypto';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { AppError } from '@/lib/types/errors';

/** Build the short-lived signed identity accepted by the private data engine. */
export async function researchIdentityHeaders(): Promise<Record<string, string>> {
  const secret = process.env.RESEARCH_AUTH_SECRET;
  if (!secret || secret.length < 32) {
    throw new AppError(
      'Research authentication is not configured',
      'RESEARCH_AUTH_NOT_CONFIGURED',
      503,
    );
  }

  const user = await requireAuthenticatedUser();
  const tenantId = user.id;
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const signature = createHmac('sha256', secret)
    .update(`${tenantId}:${user.id}:${timestamp}`)
    .digest('hex');

  return {
    'X-CavaAI-User': user.id,
    'X-CavaAI-Tenant': tenantId,
    'X-CavaAI-Timestamp': timestamp,
    'X-CavaAI-Signature': signature,
  };
}

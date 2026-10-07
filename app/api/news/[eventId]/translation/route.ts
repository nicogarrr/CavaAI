import { NextResponse } from 'next/server';
import { researchIdentityHeaders } from '@/lib/auth/research-identity';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';

export async function POST(_request: Request, { params }: { params: Promise<{ eventId: string }> }) {
  await requireAuthenticatedUser();
  const { eventId } = await params;
  if (!/^[1-9]\d*$/.test(eventId) || !Number.isSafeInteger(Number(eventId))) return NextResponse.json({status:'unavailable'}, {status:400});
  const path = `/api/news/${eventId}/translation`;
  try {
    const response = await fetch(`${process.env.FMP_BACKEND_URL ?? 'http://localhost:8000'}${path}`, {
      method: 'POST', headers: await researchIdentityHeaders({method:'POST',path}),
      cache:'no-store', signal:AbortSignal.timeout(12000),
    });
    if (!response.ok) return NextResponse.json({status:'unavailable'}, {status:response.status});
    return NextResponse.json(await response.json());
  } catch {
    return NextResponse.json({status:'unavailable'}, {status:502});
  }
}

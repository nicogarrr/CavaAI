import { NextRequest, NextResponse } from 'next/server';
import { getRankedFundsByCategory, type FundCategory } from '@/lib/actions/fundsRanking.actions';

export async function GET(req: NextRequest) {
  const category = (req.nextUrl.searchParams.get('category') || 'msci_world') as FundCategory;
  const limit = Number(req.nextUrl.searchParams.get('limit') || '10');
  try {
    const data = await getRankedFundsByCategory(category, limit);
    return NextResponse.json(data, { status: 200 });
  } catch (e) {
    if (process.env.NODE_ENV === 'development') {
      console.error('Funds rank API error', e);
    }
    return NextResponse.json({ error: 'Failed to rank funds' }, { status: 500 });
  }
}



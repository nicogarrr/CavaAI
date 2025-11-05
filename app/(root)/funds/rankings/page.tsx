import FundRankings from '@/components/funds/FundRankings';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default function Page() {
  return (
    <div className="container py-8">
      <FundRankings />
    </div>
  );
}



import { FundRankingTable } from '@/components/funds/FundRankingTable';
import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';

export default async function FundsPage() {
    const auth = await getAuth();
    const session = await auth.api.getSession({ headers: await headers() });

    if (!session) {
        redirect('/sign-in');
    }

    return (
        <div className="flex min-h-screen flex-col p-6 space-y-6">
            <div>
                <h1 className="text-3xl font-bold text-gray-100">Scanner de Fondos</h1>
                <p className="text-gray-400 mt-1">Ranking en tiempo real de los mejores fondos por categoría</p>
            </div>

            <FundRankingTable />
        </div>
    );
}

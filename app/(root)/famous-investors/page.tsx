import { getFamousInvestors } from '@/lib/actions/famousInvestors.actions';
import FamousInvestorCard from '@/components/famousInvestors/FamousInvestorCard';
import { Card } from '@/components/ui/card';
import { TrendingUp, Users } from 'lucide-react';

export default async function FamousInvestorsPage() {
    const investors = await getFamousInvestors();

    return (
        <div className="flex min-h-screen flex-col p-6">
            <div className="mb-8">
                <h1 className="text-3xl font-bold text-gray-100 mb-2">Carteras de Inversores Famosos</h1>
                <p className="text-gray-400">
                    Analiza y replica las estrategias de los inversores más exitosos del mundo
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {investors.map((investor) => (
                    <FamousInvestorCard key={investor._id} investor={investor} />
                ))}
            </div>
        </div>
    );
}


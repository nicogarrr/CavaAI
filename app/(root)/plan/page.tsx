import { Target } from 'lucide-react';
import PlanView from '@/components/plan/PlanView';
import { getPlan, getPlanContributions, getPlanDrift } from '@/lib/actions/plan.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function PlanPage() {
    const [plan, contributions, drift] = await Promise.all([
        getPlan().catch(() => null),
        getPlanContributions().catch(() => []),
        getPlanDrift().catch(() => null),
    ]);

    return (
        <main className="mx-auto flex max-w-6xl flex-col gap-6">
            <header className="flex flex-col gap-3 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
                <div>
                    <p className="text-sm font-semibold uppercase text-teal-300">Planning</p>
                    <h1 className="mt-1 text-3xl font-bold text-gray-100">Plan de Inversión</h1>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-400">
                        Tu objetivo a largo plazo, las aportaciones registradas y la desviación de la cartera frente a la asignación objetivo.
                    </p>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-gray-800 bg-[#111111] px-3 py-2 text-sm text-gray-300">
                    <Target className="h-4 w-4 text-teal-300" />
                    Plan
                </div>
            </header>

            <PlanView
                initialPlan={plan}
                initialContributions={contributions}
                initialDrift={drift}
            />
        </main>
    );
}
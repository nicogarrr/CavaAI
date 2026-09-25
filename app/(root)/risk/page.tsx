import { Gauge } from 'lucide-react';
import RiskDashboardView from '@/components/risk/RiskDashboardView';
import { getRiskDashboard } from '@/lib/actions/risk.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function RiskPage() {
    const dashboard = await getRiskDashboard().catch(() => null);

    return (
        <main className="mx-auto flex max-w-6xl flex-col gap-6">
            <header className="flex flex-col gap-3 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
                <div>
                    <p className="text-sm font-semibold uppercase text-teal-300">Riesgo</p>
                    <h1 className="mt-1 text-3xl font-bold text-gray-100">Dashboard de Riesgo</h1>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-400">
                        Volatilidad, drawdown, VaR, correlaciones y exposición por posición de tu cartera.
                    </p>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-gray-800 bg-[#111111] px-3 py-2 text-sm text-gray-300">
                    <Gauge className="h-4 w-4 text-teal-300" />
                    Riesgo
                </div>
            </header>

            <RiskDashboardView initialDashboard={dashboard} />
        </main>
    );
}
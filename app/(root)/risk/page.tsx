import type { Metadata } from 'next';
import { Gauge } from 'lucide-react';
import RiskDashboardView from '@/components/risk/RiskDashboardView';
import BackendOffline from '@/components/system/BackendOffline';
import { getRiskDashboard, type RiskDashboardRecord } from '@/lib/actions/risk.actions';
import { isBackendUnavailableError } from '@/lib/backend-offline';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
    title: 'Exposiciones de cartera',
    description:
        'Pesos, concentración (top 1 y top 5) y exposición por sector y posición de tu cartera.',
};

export default async function RiskPage() {
    let dashboard: RiskDashboardRecord;
    try {
        dashboard = await getRiskDashboard();
    } catch (error) {
        // `catch(() => null)` dejaba a RiskDashboardView sin datos: el mismo
        // texto salía para "cartera vacía" y para "motor apagado".
        if (isBackendUnavailableError(error)) {
            return <BackendOffline feature="Exposiciones de cartera" retryHref="/risk" />;
        }
        throw error;
    }

    return (
        <main id="content" tabIndex={-1} className="mx-auto flex max-w-6xl flex-col gap-6">
            <header className="flex flex-col gap-3 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
                <div>
                    <p className="text-sm font-semibold uppercase text-teal-300">Cartera · Exposiciones</p>
                    <h1 className="mt-1 text-3xl font-bold text-gray-100">Exposiciones de cartera</h1>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-400">
                        Pesos, concentración (top 1 y top 5) y exposición por sector y posición.
                        No calcula volatilidad, drawdown ni VaR: hace falta historia de precios
                        que el motor aún no usa. Para el detalle por posición, ver cartera.
                    </p>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-gray-800 bg-[#111111] px-3 py-2 text-sm text-gray-300">
                    <Gauge className="h-4 w-4 text-teal-300" />
                    Exposiciones
                </div>
            </header>

            <RiskDashboardView initialDashboard={dashboard} />
        </main>
    );
}

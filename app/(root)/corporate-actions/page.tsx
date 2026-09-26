import type { Metadata } from 'next';
import { Building2 } from 'lucide-react';
import CorporateActionsView from '@/components/corporate-actions/CorporateActionsView';
import BackendOffline from '@/components/system/BackendOffline';
import { getCorporateActions, type CorporateActionRecord } from '@/lib/actions/corporate-actions.actions';
import { isBackendUnavailableError } from '@/lib/backend-offline';
import { formatNumber } from '@/lib/format';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
    title: 'Acciones corporativas',
    description:
        'Dividendos, splits, spin-offs y fusiones: revisa los eventos pendientes y aplícalos a tu cartera.',
};

export default async function CorporateActionsPage() {
    let actions: CorporateActionRecord[];
    try {
        actions = await getCorporateActions();
    } catch (error) {
        // Antes un fallo de red se traducía en `[]` y la cuenta de eventos
        // llegaba a la pantalla: el usuario leía "0 eventos" con el motor
        // apagado, indistinguible de "no tienes eventos pendientes".
        if (isBackendUnavailableError(error)) {
            return <BackendOffline feature="Acciones Corporativas" retryHref="/corporate-actions" />;
        }
        throw error;
    }

    return (
        <main id="content" tabIndex={-1} className="mx-auto flex max-w-6xl flex-col gap-6">
            <header className="flex flex-col gap-3 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
                <div>
                    <p className="text-sm font-semibold uppercase text-teal-300">Eventos corporativos</p>
                    <h1 className="mt-1 text-3xl font-bold text-gray-100">Acciones Corporativas</h1>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-400">
                        Dividendos, splits, spin-offs y fusiones: revisa los eventos pendientes y aplícalos a tu cartera.
                    </p>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-gray-800 bg-[#111111] px-3 py-2 text-sm text-gray-300">
                    <Building2 className="h-4 w-4 text-teal-300" />
                    {formatNumber(actions.length, { maximumFractionDigits: 0 })} eventos
                </div>
            </header>

            <CorporateActionsView initialActions={actions} />
        </main>
    );
}

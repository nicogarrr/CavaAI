import { Building2 } from 'lucide-react';
import CorporateActionsView from '@/components/corporate-actions/CorporateActionsView';
import { getCorporateActions } from '@/lib/actions/corporate-actions.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function CorporateActionsPage() {
    const actions = await getCorporateActions().catch(() => []);

    return (
        <main className="mx-auto flex max-w-6xl flex-col gap-6">
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
                    {actions.length} eventos
                </div>
            </header>

            <CorporateActionsView initialActions={actions} />
        </main>
    );
}
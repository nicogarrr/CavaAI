import { BellRing } from 'lucide-react';
import AlertsManager from '@/components/alerts/AlertsManager';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function AlertsPage() {
    return (
        <main className="mx-auto flex max-w-5xl flex-col gap-6">
            <header className="flex flex-col gap-3 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
                <div>
                    <p className="text-sm font-semibold uppercase text-teal-300">Notifications</p>
                    <h1 className="mt-1 text-3xl font-bold text-gray-100">Alertas</h1>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-400">
                        Configura alertas en tiempo real sobre precios, noticias y earnings de tus acciones.
                    </p>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-gray-800 bg-[#111111] px-3 py-2 text-sm text-gray-300">
                    <BellRing className="h-4 w-4 text-teal-300" />
                    Alertas
                </div>
            </header>

            <AlertsManager />
        </main>
    );
}
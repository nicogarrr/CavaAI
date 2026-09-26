import type { Metadata } from 'next';
import { generateEnhancedProPicks, getAvailableStrategies } from '@/lib/actions/proPicks.actions';
import { Sparkles } from 'lucide-react';
import ProPicksTabs from '@/components/proPicks/ProPicksTabs';
import BackendOffline from '@/components/system/BackendOffline';
import { isBackendUnavailableError } from '@/lib/backend-offline';

// Dinámica (antes `revalidate = 3600`): con ISR, un fallo transitorio del motor
// se congelaba en la caché durante una hora y el «Reintentar» no ayudaba de
// nada. `loading.tsx` sólo tiene sentido con renderizado dinámico.
export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
    title: 'ProPicks IA',
    description:
        'Selección vigente del embudo IA sobre el universo líquido, con la fecha de datos de cada tarjeta y backtesting walk-forward aparte.',
};

export default async function ProPicksPage() {
    // Preparar picks iniciales y estrategias disponibles en paralelo
    let initialPicks: Awaited<ReturnType<typeof generateEnhancedProPicks>>;
    let strategies: Awaited<ReturnType<typeof getAvailableStrategies>>;
    try {
        [initialPicks, strategies] = await Promise.all([
            generateEnhancedProPicks({
                timePeriod: 'month',
                limit: 20,
                minScore: 70,
                sector: 'all',
                sortBy: 'score',
            }),
            getAvailableStrategies(),
        ]);
    } catch (error) {
        // Esta página es de las más frágiles cuando el motor importa: sin catch
        // el fallo subía al ErrorBoundary global.
        if (isBackendUnavailableError(error)) {
            return <BackendOffline feature="ProPicks IA" retryHref="/propicks" />;
        }
        throw error;
    }

    const generatedAt = new Date().toISOString();

    return (
        <main id="content" tabIndex={-1} className="mx-auto flex w-full min-w-0 max-w-7xl flex-col overflow-x-clip p-4 sm:p-6">
            {/* Header */}
            <div className="mb-8">
                <div className="flex items-center gap-3 mb-4">
                    <Sparkles className="h-7 w-7 shrink-0 text-teal-400 sm:h-8 sm:w-8" />
                    <div className="min-w-0">
                        <h1 className="break-words text-2xl font-bold text-gray-100 sm:text-3xl">ProPicks IA</h1>
                        <p className="text-gray-400 mt-1">
                            Selección vigente del último run del embudo, con la fecha de datos en cada tarjeta
                        </p>
                    </div>
                </div>
                <p className="text-sm text-gray-500">
                    El embudo IA evalúa el universo líquido con 6 categorías
                    (valor, crecimiento, rentabilidad, caja, momentum, salud
                    financiera) y publica aquí la selección del último run
                    con su fecha de datos en cada tarjeta. El backtest de la
                    pestaña «Backtesting» es un baseline walk-forward aparte
                    (momentum 12-1M sobre 30 valores, costes 15 pb, SPY como
                    referencia): sirve para validar el motor point-in-time,
                    no como validación de la estrategia IA.
                </p>
            </div>

            {/* Picks IA + Backtesting por estrategia */}
            <ProPicksTabs strategies={strategies} initialPicks={initialPicks} generatedAt={generatedAt} />
        </main>
    );
}

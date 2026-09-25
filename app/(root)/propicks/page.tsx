import { generateEnhancedProPicks, getAvailableStrategies } from '@/lib/actions/proPicks.actions';
import { Sparkles } from 'lucide-react';
import ProPicksTabs from '@/components/proPicks/ProPicksTabs';

// Cache for 1 hour - don't regenerate on every visit
export const revalidate = 3600;

export default async function ProPicksPage() {
    // Preparar picks iniciales y estrategias disponibles en paralelo
    const [initialPicks, strategies] = await Promise.all([
        generateEnhancedProPicks({
            timePeriod: 'month',
            limit: 20,
            minScore: 70,
            sector: 'all',
            sortBy: 'score',
        }),
        getAvailableStrategies(),
    ]);

    const generatedAt = new Date().toISOString();

    return (
        <div className="mx-auto flex min-h-screen w-full min-w-0 max-w-7xl flex-col overflow-x-clip p-4 sm:p-6">
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
                    El embudo evalúa el universo completo de acciones con datos point-in-time
                    (solo lo que era público en cada fecha) y publica aquí la selección del
                    último run. El backtest es walk-forward: cada corte mensual usa solo
                    información disponible en ese corte, con costes de 15 pb por operación
                    y SPY como referencia.
                </p>
            </div>

            {/* Picks IA + Backtesting por estrategia */}
            <ProPicksTabs strategies={strategies} initialPicks={initialPicks} generatedAt={generatedAt} />
        </div>
    );
}
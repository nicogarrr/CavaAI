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

    const currentMonth = new Date().toLocaleDateString('es-ES', { month: 'long', year: 'numeric' });
    const generatedAt = new Date().toISOString();

    return (
        <div className="flex min-h-screen flex-col p-6">
            {/* Header */}
            <div className="mb-8">
                <div className="flex items-center gap-3 mb-4">
                    <Sparkles className="h-8 w-8 text-teal-400" />
                    <div>
                        <h1 className="text-3xl font-bold text-gray-100">ProPicks IA</h1>
                        <p className="text-gray-400 mt-1">
                            Selección de acciones por Inteligencia Artificial - {currentMonth}
                        </p>
                    </div>
                </div>
                <p className="text-sm text-gray-500">
                    Nuestro sistema analiza más de 100 métricas financieras, compara con pares
                    y utiliza IA para identificar las mejores oportunidades.
                </p>
            </div>

            {/* Picks IA + Backtesting por estrategia */}
            <ProPicksTabs strategies={strategies} initialPicks={initialPicks} generatedAt={generatedAt} />
        </div>
    );
}
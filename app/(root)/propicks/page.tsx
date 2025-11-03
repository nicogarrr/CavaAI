import { generateEnhancedProPicks } from '@/lib/actions/proPicks.actions';
import { Sparkles } from 'lucide-react';
import EnhancedProPicksContent from '@/components/proPicks/EnhancedProPicksContent';

// Forzar renderizado dinámico porque requiere datos en tiempo real
export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function ProPicksPage() {
    // Generar picks iniciales con configuración por defecto
    const initialPicks = await generateEnhancedProPicks({
        timePeriod: 'month',
        limit: 20,
        minScore: 70,
        sector: 'all',
        sortBy: 'score',
    });

    const currentMonth = new Date().toLocaleDateString('es-ES', { month: 'long', year: 'numeric' });

    return (
        <div className="flex min-h-screen flex-col p-6">
            {/* Header */}
            <div className="mb-8">
                <div className="flex items-center gap-3 mb-4">
                    <Sparkles className="h-8 w-8 text-teal-400" />
                    <div>
                        <h1 className="text-3xl font-bold text-gray-100">ProPicks IA</h1>
                        <p className="text-gray-400 mt-1">
                            Las mejores acciones seleccionadas por inteligencia artificial para {currentMonth}
                        </p>
                    </div>
                </div>
                <p className="text-gray-300 max-w-4xl">
                    Sistema avanzado de selección de acciones similar a Investing Pro. Analiza más de 100 métricas 
                    financieras, compara cada acción con sus pares del sector y utiliza IA para identificar las mejores 
                    oportunidades. Filtra por período, sector, score mínimo y criterio de ordenamiento para encontrar 
                    exactamente lo que buscas.
                </p>
            </div>

            {/* Enhanced ProPicks Content with Filters */}
            <EnhancedProPicksContent initialPicks={initialPicks} />
        </div>
    );
}


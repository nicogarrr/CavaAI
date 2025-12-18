import { generateEnhancedProPicks } from '@/lib/actions/proPicks.actions';
import { Sparkles, TrendingUp } from 'lucide-react';
import EnhancedProPicksContent from '@/components/proPicks/EnhancedProPicksContent';
import GarpStrategyTable from '@/components/proPicks/GarpStrategyTable';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

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
                        <h1 className="text-3xl font-bold text-gray-100">ProPicks & Estrategias</h1>
                        <p className="text-gray-400 mt-1">
                            Selección de acciones por Inteligencia Artificial y Algoritmos Cuantitativos
                        </p>
                    </div>
                </div>
            </div>

            <Tabs defaultValue="ai" className="space-y-6">
                <TabsList className="bg-gray-800/50 border-gray-700">
                    <TabsTrigger value="ai" className="data-[state=active]:bg-teal-500/20 data-[state=active]:text-teal-400">
                        <Sparkles className="w-4 h-4 mr-2" />
                        ProPicks IA (Mensual)
                    </TabsTrigger>
                    <TabsTrigger value="garp" className="data-[state=active]:bg-blue-500/20 data-[state=active]:text-blue-400">
                        <TrendingUp className="w-4 h-4 mr-2" />
                        Top 12 Meses (GARP)
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="ai" className="space-y-4">
                    <div className="mb-6">
                        <h2 className="text-xl font-semibold text-gray-100">ProPicks IA - {currentMonth}</h2>
                        <p className="text-gray-400 text-sm">
                            Nuestro sistema analiza más de 100 métricas financieras, compara con pares y utiliza IA para identificar las mejores oportunidades.
                        </p>
                    </div>
                    {/* Enhanced ProPicks Content with Filters */}
                    <EnhancedProPicksContent initialPicks={initialPicks} />
                </TabsContent>

                <TabsContent value="garp" className="space-y-4">
                    <GarpStrategyTable />
                </TabsContent>
            </Tabs>
        </div>
    );
}


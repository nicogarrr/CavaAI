import { getPortfolioPerformance } from '@/lib/actions/portfolio.actions';
import { notFound } from 'next/navigation';
import PortfolioHeader from '@/components/portfolio/PortfolioHeader';
import PortfolioSummary from '@/components/portfolio/PortfolioSummary';
import PositionsTable from '@/components/portfolio/PositionsTable';
import AddPositionButton from '@/components/portfolio/AddPositionButton';
import PortfolioAllocation from '@/components/portfolio/PortfolioAllocation';
import PortfolioHistoryChart from '@/components/portfolio/PortfolioHistoryChart';
import { getPortfolioHistory } from '@/lib/actions/portfolio.actions';
import PortfolioAISummary from '@/components/portfolio/PortfolioAISummary';
import PortfolioStatus from '@/components/portfolio/PortfolioStatus';
import PortfolioNews from '@/components/portfolio/PortfolioNews';

type PortfolioDetailPageProps = {
    params: Promise<{
        id: string;
    }>;
};

export default async function PortfolioDetailPage({ params }: PortfolioDetailPageProps) {
    const { id } = await params;

    try {
        const data = await getPortfolioPerformance(id);
        const history = await getPortfolioHistory(id, 365);

        if (!data) {
            notFound();
        }

        return (
            <div className="flex min-h-screen flex-col p-6">
                <PortfolioHeader portfolio={data.portfolio} />

                {/* Solo mostrar status si hay problemas */}
                {data.status.mockDataCount > 0 || !data.status.hasApiKey ? (
                    <PortfolioStatus 
                        hasApiKey={data.status.hasApiKey}
                        isOnline={data.status.isOnline}
                        mockDataCount={data.status.mockDataCount}
                        totalPositions={data.status.totalPositions}
                    />
                ) : null}

                <div className="mt-6 mb-8">
                    <PortfolioSummary summary={data.summary} />
                </div>

                {/* Layout principal: métricas clave y gráficos */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                    {/* Columna principal: Tabla de posiciones y gráfico */}
                    <div className="lg:col-span-2 space-y-6">
                        {/* Distribución de la cartera */}
                        <PortfolioAllocation positions={data.positions} />
                        
                        {/* Histórico */}
                        <PortfolioHistoryChart data={history} />
                    </div>

                    {/* Sidebar: Noticias */}
                    <div className="space-y-6">
                        <PortfolioNews portfolioId={id} />
                    </div>
                </div>

                {/* Resumen con IA (opcional, se puede colapsar) */}
                <div className="mb-8">
                    <PortfolioAISummary portfolio={data} history={history} />
                </div>

                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-2xl font-semibold">Posiciones</h2>
                    <AddPositionButton portfolioId={id} />
                </div>

                <PositionsTable positions={data.positions} portfolioId={id} />
            </div>
        );
    } catch (error) {
        console.error('Error loading portfolio:', error);
        notFound();
    }
}


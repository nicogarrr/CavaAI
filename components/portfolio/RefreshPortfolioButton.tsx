'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { RefreshCw, Loader2 } from 'lucide-react';
import { updateAllPortfolioPrices } from '@/lib/actions/portfolio.actions';
import { toast } from 'sonner';
import { showErrorToast } from '@/lib/toast';

interface RefreshPortfolioButtonProps {
    userId: string;
}

export default function RefreshPortfolioButton({ userId }: RefreshPortfolioButtonProps) {
    const [isRefreshing, setIsRefreshing] = useState(false);
    const router = useRouter();

    async function handleFullRefresh() {
        try {
            setIsRefreshing(true);

            // Invalida las lecturas cacheadas (15 s) y las relee del backend.
            // NO dispara POST /api/portfolio/refresh-market: ese endpoint
            // refresca el universo completo de empresas del tenant y tarda
            // minutos, así que aquí solo se releen los datos que el servidor
            // tiene guardados.
            await updateAllPortfolioPrices(userId);

            // Vuelve a renderizar los KPIs del servidor con lo releído.
            router.refresh();
            // El toast dice lo que pasó: lecturas rehechas contra el servidor.
            // «Cartera actualizada» afirmaba precios nuevos que este botón no
            // puede pedir.
            toast.success('Lecturas de cartera actualizadas');

        } catch (error) {
            showErrorToast(error, { onRetry: handleFullRefresh });
        } finally {
            // Small delay to allow the page to refresh
            setTimeout(() => setIsRefreshing(false), 1000);
        }
    }

    return (
        <Button
            variant="outline"
            size="sm"
            onClick={handleFullRefresh}
            disabled={isRefreshing}
            aria-busy={isRefreshing}
            title="Vuelve a leer posiciones y KPIs del servidor, sin caché. No fuerza cotizaciones nuevas: los precios son los últimos que guardó el servidor."
            className="border-gray-600 hover:bg-gray-700 text-gray-200"
        >
            {isRefreshing ? (
                <>
                    <Loader2 aria-hidden="true" className="mr-2 h-4 w-4 animate-spin" />
                    Actualizando...
                </>
            ) : (
                <>
                    <RefreshCw aria-hidden="true" className="mr-2 h-4 w-4" />
                    Actualizar Todo
                </>
            )}
        </Button>
    );
}

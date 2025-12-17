'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { RefreshCw, Loader2 } from 'lucide-react';
import { updateAllPortfolioPrices } from '@/lib/actions/portfolio.actions';

interface RefreshPortfolioButtonProps {
    userId: string;
}

export default function RefreshPortfolioButton({ userId }: RefreshPortfolioButtonProps) {
    const [isRefreshing, setIsRefreshing] = useState(false);
    const router = useRouter();

    async function handleFullRefresh() {
        try {
            setIsRefreshing(true);

            // 1. Update all stock prices in holdings
            await updateAllPortfolioPrices(userId);

            // 2. Force a full page refresh to recalculate all KPIs
            router.refresh();

        } catch (error) {
            console.error('Error refreshing portfolio:', error);
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
            className="border-gray-600 hover:bg-gray-700 text-gray-200"
        >
            {isRefreshing ? (
                <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Actualizando...
                </>
            ) : (
                <>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Actualizar Todo
                </>
            )}
        </Button>
    );
}

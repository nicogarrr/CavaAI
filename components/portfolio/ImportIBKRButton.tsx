'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Loader2, Landmark } from 'lucide-react';
import { importFromIBKR } from '@/lib/actions/portfolio.actions';
import { toast } from 'sonner';
import { getErrorMessage } from '@/lib/types/errors';

interface ImportIBKRButtonProps {
    userId: string;
}

export default function ImportIBKRButton({ userId }: ImportIBKRButtonProps) {
    const [isImporting, setIsImporting] = useState(false);
    const router = useRouter();

    async function handleImport() {
        try {
            setIsImporting(true);
            const result = await importFromIBKR(userId);

            if (result.status !== 'imported') {
                toast.error(`Importación falló: ${result.status}`);
                return;
            }

            toast.success(
                `IBKR: ${result.positions_imported} posiciones, ${result.trades_imported} operaciones, ` +
                `${result.dividends_imported} dividendos, ${result.fees_imported} comisiones, ` +
                `${result.cash_imported} cuentas de efectivo`
            );
            router.refresh();
        } catch (error) {
            toast.error(getErrorMessage(error));
        } finally {
            // Small delay to allow the page to refresh
            setTimeout(() => setIsImporting(false), 1000);
        }
    }

    return (
        <Button
            variant="outline"
            size="sm"
            onClick={handleImport}
            disabled={isImporting}
            className="border-gray-600 hover:bg-gray-700 text-gray-200"
            title="Importar cartera desde Interactive Brokers (Flex statement)"
        >
            {isImporting ? (
                <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Importando IBKR...
                </>
            ) : (
                <>
                    <Landmark className="mr-2 h-4 w-4" />
                    Importar IBKR
                </>
            )}
        </Button>
    );
}
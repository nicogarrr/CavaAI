'use client';

import { useState } from 'react';
import { FileText, Receipt, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { RecordDetail, RecordList, type DataRecord } from '@/components/data/RecordViews';
import { getTaxHoldings, getTaxReport, regenerateTaxReport } from '@/lib/actions/taxes.actions';
import { getErrorMessage } from '@/lib/types/errors';
import { toast } from 'sonner';

interface TaxesViewProps {
    initialHoldings: DataRecord[];
    initialReport: DataRecord | null;
    year: number;
}

export default function TaxesView({ initialHoldings, initialReport, year }: TaxesViewProps) {
    const [regenerating, setRegenerating] = useState(false);

    const handleRegenerate = async () => {
        setRegenerating(true);
        try {
            await regenerateTaxReport(year);
            toast.success(`Reporte fiscal ${year} regenerado`);
        } catch (error) {
            toast.error(getErrorMessage(error));
        } finally {
            setRegenerating(false);
        }
    };

    return (
        <div className="grid gap-6">
            <RecordDetail
                title={`Reporte Fiscal ${year}`}
                description="Resumen de impuestos del ejercicio anual"
                icon={<FileText className="h-5 w-5 text-teal-400" />}
                record={initialReport}
                fetchRecord={() => getTaxReport(year)}
                emptyMessage="Sin reporte fiscal disponible para este año. Pulsa «Regenerar» para generarlo."
                actions={(
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={handleRegenerate}
                        disabled={regenerating}
                        className="gap-2 border-gray-600 text-gray-300 hover:text-teal-400"
                    >
                        <RotateCcw className={`h-4 w-4 ${regenerating ? 'animate-spin' : ''}`} />
                        Regenerar
                    </Button>
                )}
            />

            <RecordList
                title="Posiciones Fiscales"
                description="Holdings con base de coste, plusvalías latentes y retenciones"
                icon={<Receipt className="h-5 w-5 text-teal-400" />}
                records={initialHoldings}
                fetchRecords={getTaxHoldings}
                columns={['ticker', 'quantity', 'cost_basis', 'market_value', 'unrealized_pnl', 'currency']}
                emptyMessage="Aún no hay posiciones con datos fiscales. Cuando compres valores aparecerán aquí."
            />
        </div>
    );
}
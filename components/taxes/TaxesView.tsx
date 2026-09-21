'use client';

import { useState } from 'react';
import { Download, FileText, Receipt, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
    RecordDetail,
    RecordList,
    formatRecordValue,
    researchHrefFor,
    type DataRecord,
} from '@/components/data/RecordViews';
import { getTaxHoldings, getTaxReport, regenerateTaxReport } from '@/lib/actions/taxes.actions';
import { getErrorMessage } from '@/lib/types/errors';
import { toast } from 'sonner';

interface TaxesViewProps {
    initialHoldings: DataRecord[];
    initialReport: DataRecord | null;
    year: number;
}

function csvCell(value: string): string {
    return `"${value.replaceAll('"', '""')}"`;
}

/** Descarga un resumen fiscal (reporte + posiciones) como CSV generado en cliente */
function downloadTaxSummary(holdings: DataRecord[], report: DataRecord | null, year: number) {
    const lines: string[] = [`reporte_fiscal,${year}`, ''];
    lines.push('seccion,clave,valor');
    if (report) {
        for (const [key, value] of Object.entries(report)) {
            lines.push(`reporte,${csvCell(key)},${csvCell(formatRecordValue(value))}`);
        }
    } else {
        lines.push('reporte,sin_reporte,Sin reporte fiscal disponible');
    }
    lines.push('');
    if (holdings.length > 0) {
        const headers = Array.from(
            new Set(holdings.flatMap((holding) => Object.keys(holding))),
        ).slice(0, 12);
        lines.push(headers.map(csvCell).join(','));
        for (const holding of holdings) {
            lines.push(
                headers.map((header) => csvCell(formatRecordValue(holding[header]))).join(','),
            );
        }
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `resumen-fiscal-${year}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
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
                actions={
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
                }
            />

            <RecordList
                title="Posiciones Fiscales"
                description="Holdings con base de coste, plusvalías latentes y retenciones"
                icon={<Receipt className="h-5 w-5 text-teal-400" />}
                records={initialHoldings}
                fetchRecords={getTaxHoldings}
                columns={['ticker', 'quantity', 'cost_basis', 'market_value', 'unrealized_pnl', 'currency']}
                emptyMessage="Aún no hay posiciones con datos fiscales. Cuando compres valores aparecerán aquí."
                linkColumns={{ ticker: (record) => researchHrefFor(record) }}
                footer={
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                            downloadTaxSummary(initialHoldings, initialReport, year);
                            toast.success(`Resumen fiscal ${year} exportado`);
                        }}
                        disabled={initialHoldings.length === 0 && !initialReport}
                        className="gap-2 border-gray-600 text-gray-300 hover:text-teal-400"
                    >
                        <Download className="h-4 w-4" />
                        Exportar resumen
                    </Button>
                }
            />
        </div>
    );
}

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
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
import { showErrorToast } from '@/lib/toast';
import { toast } from 'sonner';

interface TaxesViewProps {
    initialHoldings: DataRecord[];
    initialReport: DataRecord | null;
    year: number;
}

/** El endpoint envuelve las métricas en {summary, dividends, realized, misc}:
 *  para mostrarlas se aplana `summary` (métricas fiscales legibles) y se
 *  conserva generated_at; las listas crudas no se pintan como JSON. */
function toDisplayReport(raw: DataRecord | null): DataRecord | null {
    if (!raw || typeof raw !== 'object') return null;
    const summary = raw.summary;
    if (summary === null || typeof summary !== 'object' || Array.isArray(summary)) return raw;
    const display: DataRecord = { ...(summary as DataRecord) };
    if (raw.generated_at) display.generated_at = raw.generated_at;
    return display;
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
    const router = useRouter();
    const [regenerating, setRegenerating] = useState(false);
    const [report, setReport] = useState<DataRecord | null>(initialReport);
    const [reportKey, setReportKey] = useState(0);

    const handleYearChange = (next: string) => {
        const parsed = Number.parseInt(next, 10);
        if (!Number.isInteger(parsed)) return;
        router.push(`/taxes?year=${parsed}`);
    };

    const handleRegenerate = async () => {
        setRegenerating(true);
        try {
            await regenerateTaxReport(year);
            // Recarga el reporte recien regenerado (POST regenerate) para que
            // la vista muestre los datos nuevos sin recarga manual.
            const fresh = (await getTaxReport(year).catch(() => null)) as DataRecord | null;
            if (fresh) {
                setReport(fresh);
                setReportKey((key) => key + 1);
            } else {
                router.refresh();
            }
            toast.success(`Reporte fiscal ${year} regenerado`);
        } catch (error) {
            showErrorToast(error, { onRetry: handleRegenerate });
        } finally {
            setRegenerating(false);
        }
    };

    const currentYear = new Date().getFullYear();
    const yearOptions = Array.from({ length: 6 }, (_, index) => currentYear - index);

    return (
        <div className="grid gap-6">
            <div className="flex flex-wrap items-center gap-3">
                <label htmlFor="tax-year" className="text-sm text-gray-400">
                    Ejercicio
                </label>
                <select
                    id="tax-year"
                    value={year}
                    onChange={(event) => handleYearChange(event.target.value)}
                    className="h-9 rounded-md border border-gray-800 bg-black px-3 text-sm text-gray-200"
                >
                    {yearOptions.map((option) => (
                        <option key={option} value={option}>
                            {option}
                        </option>
                    ))}
                </select>
            </div>
            <RecordDetail
                key={reportKey}
                title={`Reporte Fiscal ${year}`}
                description="Resumen de impuestos del ejercicio anual"
                icon={<FileText className="h-5 w-5 text-teal-400" />}
                record={toDisplayReport(report)}
                fetchRecord={async () => toDisplayReport((await getTaxReport(year)) as DataRecord | null)}
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

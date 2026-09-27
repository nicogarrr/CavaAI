'use client';

import { useEffect, useState } from 'react';
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
import { formatUserDateTime, formatMoney, NA } from '@/lib/format';
import { t } from '@/lib/i18n/t';
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
    return humanizeTaxReport(display);
}

/** Etiquetas en español para las claves conocidas del resumen fiscal (F20).
 *  Las claves desconocidas se humanizan (snake_case -> frase) sin ocultarse. */
const TAX_LABELS: Record<string, string> = {
    fiscal_year: 'Ejercicio',
    base_currency: 'Divisa base',
    total_dividends_base: 'Dividendos brutos',
    total_withholding_base: 'Retenciones soportadas',
    total_realized_gain_base: 'Plusvalías/minusvalías realizadas',
    total_blocked_loss_base: 'Minusvalías bloqueadas (regla de los 2 meses)',
    net_taxable_base: 'Base neta estimada',
    wash_sale_rule: 'Regla anti-recompra',
    wash_sale_window_open: 'Ventana anti-recompra abierta en',
    dividend_count: 'Dividendos (nº)',
    sell_count: 'Ventas (nº)',
    over_sell: 'Ventas sin compras que las cubran',
    method: 'Método de valoración',
    incomplete_fx: 'Tipos de cambio incompletos',
    missing_fx: 'Sin tipo de cambio para',
    generated_at: 'Generado',
};

const WASH_RULE_LABELS: Record<string, string> = {
    'es-irpf-2m': 'IRPF español: no recomprar en 2 meses',
};

function humanizeKey(key: string): string {
    const known = TAX_LABELS[key];
    if (known) return known;
    const words = key.replaceAll('_', ' ').trim();
    return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Convierte el resumen fiscal a filas etiquetadas en español con valores
 *  formateados (importes con divisa, listas de tickers, fechas). Nunca
 *  inventa: los null quedan como `NA` («N/D») y las claves raras se
 *  humanizan. */
function humanizeTaxReport(summary: DataRecord): DataRecord {
    const currency = typeof summary.base_currency === 'string' && summary.base_currency
        ? summary.base_currency
        : 'EUR';
    const moneyKeys = new Set([
        'total_dividends_base',
        'total_withholding_base',
        'total_realized_gain_base',
        'total_blocked_loss_base',
        'net_taxable_base',
    ]);
    const listKeys = new Set(['wash_sale_window_open', 'over_sell', 'missing_fx']);
    const display: DataRecord = {};
    for (const [key, value] of Object.entries(summary)) {
        const label = humanizeKey(key);
        if (moneyKeys.has(key)) {
            display[label] = value === null || value === undefined
                ? `${NA} (faltan tipos de cambio)`
                : formatMoney(value as number | string, currency);
        } else if (listKeys.has(key)) {
            display[label] = Array.isArray(value) && value.length > 0 ? value.join(', ') : 'Ninguno';
        } else if (key === 'wash_sale_rule') {
            display[label] = WASH_RULE_LABELS[String(value)] ?? String(value);
        } else if (key === 'generated_at') {
            display[label] = formatUserDateTime(value as string);
        } else if (typeof value === 'boolean') {
            display[label] = value ? 'Sí' : 'No';
        } else {
            display[label] = value;
        }
    }
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

    // El año civil viene del reloj del navegador: leerlo en el render rompe la
    // hidratación en la frontera de año. Se arranca con un estado fijo (0) y se
    // fija el año real en el primer efecto.
    const [currentYear, setCurrentYear] = useState(0);
    useEffect(() => {
        setCurrentYear(new Date().getFullYear());
    }, []);
    const yearOptions = currentYear === 0
        ? []
        : Array.from({ length: 6 }, (_, index) => currentYear - index);

    return (
        <div className="grid gap-6">
            <div className="flex flex-wrap items-center gap-3">
                <label htmlFor="tax-year" className="text-sm text-gray-400">
                    {t('taxes.year')}
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
                hiddenKeys={['trace']}
                record={toDisplayReport(report)}
                fetchRecord={async () => toDisplayReport((await getTaxReport(year)) as DataRecord | null)}
                emptyMessage={t('taxes.noReport')}
                actions={
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={handleRegenerate}
                        disabled={regenerating}
                        className="gap-2 border-gray-600 text-gray-300 hover:text-teal-400"
                    >
                        <RotateCcw className={`h-4 w-4 ${regenerating ? 'animate-spin' : ''}`} />
                        {t('taxes.regenerate')}
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

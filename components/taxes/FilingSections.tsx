'use client';

import { Landmark, FileDown, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatMoney, NA } from '@/lib/format';
import { toast } from 'sonner';

/**
 * Secciones de declaración de la página Impuestos (Modelo 100 + Modelo 720).
 *
 * Cohesión: misma gramática visual que el resto de la vista (paneles con
 * borde gray-800, acentos teal). Honestidad: todo número viene del backend;
 * los estados sin datos se declaran (available=false, tri-estado
 * «desconocido», badges «estimativo») y nunca se presenta nada como listo
 * para declarar.
 */

type DataRecord = Record<string, unknown>;

const CATEGORY_LABELS: Record<string, string> = {
    valores: 'Valores en el extranjero',
    cuentas: 'Cuentas en el extranjero',
    inmuebles: 'Inmuebles en el extranjero',
};

const STATUS_CHIP: Record<string, { label: string; className: string }> = {
    supera: { label: 'Supera el umbral de 50.000 €', className: 'border-amber-700 text-amber-300' },
    por_debajo: { label: 'Por debajo del umbral', className: 'border-teal-800 text-teal-300' },
    desconocido: { label: 'No concluyente (faltan datos)', className: 'border-gray-600 text-gray-300' },
    no_evaluable: { label: 'No evaluable con datos de bróker', className: 'border-gray-700 text-gray-500' },
};

function money(value: unknown): string {
    if (value === null || value === undefined) return NA;
    return formatMoney(value as number | string, 'EUR');
}

/** Descarga el fichero 720 en ISO-8859-1 (la spec AEAT; el backend ya
 *  sanea el contenido a caracteres latin-1). */
function downloadModelo720(content: string, year: number) {
    const bytes = new Uint8Array(
        Array.from(content, (ch) => {
            const code = ch.codePointAt(0) ?? 0;
            return code <= 0xff ? code : 0x3f; // '?' (no debería ocurrir: backend sanea)
        }),
    );
    const blob = new Blob([bytes], { type: 'text/plain;charset=iso-8859-1' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `modelo720_${year}.txt`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
}

function Section({ title, description, icon, children }: {
    title: string;
    description: string;
    icon: React.ReactNode;
    children: React.ReactNode;
}) {
    return (
        <section className="rounded-lg border border-gray-800 bg-gray-950/40 p-5">
            <header className="mb-4 flex items-start gap-3">
                <span className="mt-0.5">{icon}</span>
                <div>
                    <h2 className="text-lg font-semibold text-gray-100">{title}</h2>
                    <p className="mt-1 text-sm leading-6 text-gray-400">{description}</p>
                </div>
            </header>
            {children}
        </section>
    );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
    return (
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-gray-800/60 py-2 text-sm last:border-0">
            <span className="text-gray-400">{label}</span>
            <span className="text-right text-gray-200">{value}</span>
        </div>
    );
}

function Chip({ status }: { status: string }) {
    const chip = STATUS_CHIP[status] ?? STATUS_CHIP.desconocido;
    return (
        <span className={`inline-block rounded-full border px-2 py-0.5 text-xs ${chip.className}`}>
            {chip.label}
        </span>
    );
}

function WarningList({ items }: { items: string[] }) {
    if (items.length === 0) return null;
    return (
        <ul className="mt-3 space-y-1 text-xs leading-5 text-amber-200/80">
            {items.map((item) => (
                <li key={item} className="flex gap-2">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span>{item}</span>
                </li>
            ))}
        </ul>
    );
}

export function FilingSection({ filing }: { filing: DataRecord | null }) {
    if (!filing) return null;
    if (filing.available === false) {
        return (
            <Section
                title="Declaración (Modelo 100)"
                description="Casillas orientativas del IRPF calculadas desde tu cartera."
                icon={<Landmark className="h-5 w-5 text-teal-400" />}
            >
                <p className="text-sm text-gray-400">{String(filing.reason ?? 'No disponible para este ejercicio.')}</p>
            </Section>
        );
    }
    const casillas = (filing.casillas ?? {}) as DataRecord;
    const acciones = (casillas.acciones_negociadas ?? {}) as DataRecord;
    const dividendos = (casillas.dividendos ?? {}) as DataRecord;
    const dt = (filing.double_taxation ?? {}) as DataRecord;
    const lc = (filing.loss_compensation ?? {}) as DataRecord;
    const manualReview = Array.isArray(dt.manual_review) ? dt.manual_review as DataRecord[] : [];
    const specialTickers = Array.isArray(dividendos.special_payment_tickers)
        ? dividendos.special_payment_tickers as string[]
        : [];
    const warnings: string[] = [
        ...manualReview.map((item) => `${String(item.ticker ?? '')}: ${String(item.reason ?? '')}`),
        ...(specialTickers.length > 0
            ? [`Pagos especiales fuera de los dividendos ordinarios (revisión manual): ${specialTickers.join(', ')}`]
            : []),
    ];
    return (
        <Section
            title="Declaración (Modelo 100)"
            description="Casillas orientativas del IRPF calculadas desde tu cartera. Ayuda de cómputo: no apto para declarar sin la validación de un asesor fiscal."
            icon={<Landmark className="h-5 w-5 text-teal-400" />}
        >
            <div className="grid gap-1">
                <Row label="0328 · Transmisión global" value={money(acciones['0328_transmision_global'])} />
                <Row label="0331 · Adquisición global" value={money(acciones['0331_adquisicion_global'])} />
                <Row label="0339 · Suma de ganancias" value={money(acciones['0339_suma_ganancias'])} />
                <Row label="0340 · Suma de pérdidas" value={money(acciones['0340_suma_perdidas'])} />
                <Row label="0029 · Dividendos íntegros" value={money(dividendos['0029_ingresos_integros'])} />
                <Row
                    label="0588 · Deducción por doble imposición"
                    value={
                        dt.status === 'pendiente_tme'
                            ? 'Pendiente: introduce el tipo medio efectivo de tu borrador para calcularla'
                            : money(dt.total_deduction_base)
                    }
                />
                {lc && Object.keys(lc).length > 0 && (
                    <Row
                        label="Compensación de pérdidas de años anteriores"
                        value={
                            lc.estimativo === true
                                ? `Estimativa (no trasladable a casillas): restan ${money(lc.remaining_to_carry_base)} por arrastrar`
                                : `Aplicada: ${money(lc.applied_to_gains_total_base)} a ganancias y ${money(lc.applied_to_income_total_base)} a rendimientos`
                        }
                    />
                )}
            </div>
            <WarningList items={warnings} />
        </Section>
    );
}

export function Modelo720Section({ thresholds, file720, year }: {
    thresholds: DataRecord | null;
    file720: DataRecord | null;
    year: number;
}) {
    if (!thresholds) return null;
    const categories = (thresholds.categories ?? {}) as DataRecord;
    const missingIsin = ((categories.valores as DataRecord | undefined)?.missing_isin ?? []) as string[];
    const foreignUnverified = (thresholds.foreign_unverified ?? []) as DataRecord[];
    const shortPositions = (thresholds.short_positions ?? []) as DataRecord[];
    const unvalued = (thresholds.unvalued ?? []) as DataRecord[];
    const warnings: string[] = [
        ...(missingIsin.length > 0 ? [`Sin ISIN (necesario para declarar el valor): ${missingIsin.join(', ')}`] : []),
        ...foreignUnverified.map((item) => `${String(item.ticker ?? '')}: ${String(item.reason ?? '')}`),
        ...shortPositions.map((item) => `${String(item.ticker ?? '')}: posición corta, no cuenta como bien en el 720`),
        ...unvalued.map((item) => `${String(item.ticker ?? '')}: ${String(item.reason ?? '')}`),
    ];
    return (
        <Section
            title="Modelo 720 (bienes en el extranjero)"
            description="Chequeo orientativo del umbral de 50.000 € por categoría. Un «no concluyente» no es un «no»: falta algún dato para afirmarlo."
            icon={<Landmark className="h-5 w-5 text-teal-400" />}
        >
            <div className="grid gap-1">
                {(['valores', 'cuentas', 'inmuebles'] as const).map((key) => {
                    const category = categories[key] as DataRecord | undefined;
                    if (!category) return null;
                    return (
                        <div key={key} className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800/60 py-2 text-sm last:border-0">
                            <span className="text-gray-400">{CATEGORY_LABELS[key]}</span>
                            <span className="flex items-center gap-3">
                                <span className="text-gray-200">{money(category.total_base)}</span>
                                <Chip status={String(category.status ?? 'desconocido')} />
                            </span>
                        </div>
                    );
                })}
            </div>
            {file720 && (
                <div className="mt-4 border-t border-gray-800 pt-4">
                    {file720.available === true ? (
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <p className="text-sm text-gray-400">
                                Fichero generado ({String(file720.detail_records)} registros de detalle, formato oficial AEAT). Revísalo antes de presentarlo por TGVI Online: es una ayuda de cómputo.
                            </p>
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                    downloadModelo720(String(file720.content ?? ''), year);
                                    toast.success(`Fichero Modelo 720 ${year} descargado`);
                                }}
                                className="gap-2 border-gray-600 text-gray-300 hover:text-teal-400"
                            >
                                <FileDown className="h-4 w-4" />
                                Descargar fichero 720
                            </Button>
                        </div>
                    ) : (
                        <p className="text-sm text-gray-400">
                            Fichero no disponible: {String(file720.reason ?? 'faltan datos')}.
                        </p>
                    )}
                </div>
            )}
            <WarningList items={warnings} />
        </Section>
    );
}

import type { Metadata } from 'next';
import { Receipt } from 'lucide-react';
import TaxesView from '@/components/taxes/TaxesView';
import BackendOffline from '@/components/system/BackendOffline';
import { getTaxHoldings, getTaxReport, type TaxRecord } from '@/lib/actions/taxes.actions';
import { isBackendUnavailableError } from '@/lib/backend-offline';
import { isAppError } from '@/lib/types/errors';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
    title: 'Impuestos',
    description:
        'Posiciones con base de coste, reportes fiscales anuales y plusvalías latentes de tu cartera.',
};

type PageProps = {
    searchParams: Promise<{ year?: string }>;
};

const MIN_YEAR = 2000;
const MAX_YEAR = 2200;

/** Una lectura que aísla su fallo: null es "no hay dato", no "backend caído". */
type Read<T> = { value: T; error: unknown };

function read<T>(promise: Promise<T>, fallback: T): Promise<Read<T>> {
    return promise
        .then((value) => ({ value, error: null }))
        .catch((error: unknown) => ({ value: fallback, error }));
}

/**
 * Un 4xx NO es el motor caído: es "este recurso no existe todavía" (por
 * ejemplo, no hay reporte fiscal para el ejercicio pedido). Se traduce al
 * estado vacío de la vista; el 5xx y el fetch fallido sí son BackendOffline.
 */
function isNotGeneratedYet(error: unknown): boolean {
    return isAppError(error) && error.statusCode >= 400 && error.statusCode < 500;
}

function asFiscalYear(raw: string | undefined): number {
    const current = new Date().getFullYear();
    const parsed = raw ? Number.parseInt(raw, 10) : current;
    if (!Number.isInteger(parsed) || parsed < MIN_YEAR || parsed > MAX_YEAR) return current;
    return parsed;
}

export default async function TaxesPage({ searchParams }: PageProps) {
    const fiscalYear = asFiscalYear((await searchParams)?.year);
    const [holdingsRead, reportRead] = await Promise.all([
        read(getTaxHoldings(), [] as TaxRecord[]),
        read(getTaxReport(fiscalYear), null as TaxRecord | null),
    ]);
    const { error: holdingsError } = holdingsRead;
    const { error: reportError } = reportRead;

    if (
        (holdingsError && isBackendUnavailableError(holdingsError)) ||
        (reportError && isBackendUnavailableError(reportError))
    ) {
        return <BackendOffline feature="El informe fiscal" retryHref={`/taxes?year=${fiscalYear}`} />;
    }
    if (holdingsError && !isNotGeneratedYet(holdingsError)) throw holdingsError;
    if (reportError && !isNotGeneratedYet(reportError)) throw reportError;

    // Cualquier otro fallo es un 4xx: el ejercicio no está generado todavía y
    // la vista ofrece su propio estado vacío con «Regenerar».
    const holdings = holdingsError ? [] : holdingsRead.value;
    const report = reportError ? null : reportRead.value;

    return (
        <main id="content" tabIndex={-1} className="mx-auto flex max-w-6xl flex-col gap-6">
            <header className="flex flex-col gap-3 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
                <div>
                    <p className="text-sm font-semibold uppercase text-teal-300">Fiscal</p>
                    <h1 className="mt-1 text-3xl font-bold text-gray-100">Impuestos</h1>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-400">
                        Posiciones con base de coste, reportes fiscales anuales y plusvalías latentes de tu cartera.
                    </p>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-gray-800 bg-[#111111] px-3 py-2 text-sm text-gray-300">
                    <Receipt className="h-4 w-4 text-teal-300" />
                    Ejercicio {fiscalYear}
                </div>
            </header>

            <TaxesView initialHoldings={holdings} initialReport={report} year={fiscalYear} />
        </main>
    );
}

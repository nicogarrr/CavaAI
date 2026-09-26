import { Receipt } from 'lucide-react';
import TaxesView from '@/components/taxes/TaxesView';
import { getTaxHoldings, getTaxReport } from '@/lib/actions/taxes.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type PageProps = {
    searchParams: Promise<{ year?: string }>;
};

const MIN_YEAR = 2000;
const MAX_YEAR = 2200;

function asFiscalYear(raw: string | undefined): number {
    const current = new Date().getFullYear();
    const parsed = raw ? Number.parseInt(raw, 10) : current;
    if (!Number.isInteger(parsed) || parsed < MIN_YEAR || parsed > MAX_YEAR) return current;
    return parsed;
}

export default async function TaxesPage({ searchParams }: PageProps) {
    const fiscalYear = asFiscalYear((await searchParams)?.year);
    const [holdings, report] = await Promise.all([
        getTaxHoldings().catch(() => []),
        getTaxReport(fiscalYear).catch(() => null),
    ]);

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

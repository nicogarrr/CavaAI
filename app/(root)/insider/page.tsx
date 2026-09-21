import { Users } from 'lucide-react';
import InsiderSignalsView from '@/components/insider/InsiderSignalsView';
import { getInsiderSignals } from '@/lib/actions/insider.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type PageProps = {
    searchParams: Promise<{ ticker?: string }>;
};

export default async function InsiderPage({ searchParams }: PageProps) {
    const { ticker: rawTicker } = await searchParams;
    const ticker = rawTicker?.trim().toUpperCase() || null;
    const result = ticker ? await getInsiderSignals(ticker).catch(() => null) : null;

    return (
        <main className="mx-auto flex max-w-6xl flex-col gap-6">
            <header className="flex flex-col gap-3 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
                <div>
                    <p className="text-sm font-semibold uppercase text-teal-300">Insider</p>
                    <h1 className="mt-1 text-3xl font-bold text-gray-100">Señales Insider</h1>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-400">
                        Compras en mercado abierto (Form 4, SEC EDGAR): clusters de insiders,
                        compras de CEO/CFO y grandes operaciones. Cada ticker enlaza a su ficha de research.
                    </p>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-gray-800 bg-[#111111] px-3 py-2 text-sm text-gray-300">
                    <Users className="h-4 w-4 text-teal-300" />
                    Form 4
                </div>
            </header>

            <InsiderSignalsView initialTicker={ticker ?? ''} initialResult={result} />
        </main>
    );
}

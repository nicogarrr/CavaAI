import { Users } from 'lucide-react';
import InsiderSignalsView from '@/components/insider/InsiderSignalsView';
import { getInsiderFilings, getInsiderSignals } from '@/lib/actions/insider.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type PageProps = {
    searchParams: Promise<{ ticker?: string }>;
};

export default async function InsiderPage({ searchParams }: PageProps) {
    const { ticker: rawTicker } = await searchParams;
    const ticker = rawTicker?.trim().toUpperCase() || null;
    const [signals, filings] = ticker
        ? await Promise.all([
              getInsiderSignals(ticker).catch(() => null),
              getInsiderFilings(ticker).catch(() => null),
          ])
        : [null, null];

    return (
        <main id="content" tabIndex={-1} className="mx-auto flex w-full min-w-0 max-w-6xl flex-col gap-6 overflow-x-clip">
            <header className="flex flex-col gap-3 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
                <div>
                    <p className="text-sm font-semibold uppercase text-teal-300">Insider</p>
                    <h1 className="mt-1 text-3xl font-bold text-gray-100">Señales Insider</h1>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-400">
                        Compras insider codigo P (Form 4, SEC EDGAR; mercado abierto o privado,
                        el XML no siempre lo distingue): clusters de insiders, compras de CEO/CFO
                        y grandes operaciones. El monitor automático revisa tu watchlist y cartera
                        cada 15 minutos; esta vista es una lectura bajo demanda por ticker.
                    </p>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-gray-800 bg-[#111111] px-3 py-2 text-sm text-gray-300">
                    <Users className="h-4 w-4 text-teal-300" />
                    Form 4
                </div>
            </header>

            <InsiderSignalsView
                initialTicker={ticker ?? ''}
                initialResult={signals}
                initialFilings={filings}
            />
        </main>
    );
}

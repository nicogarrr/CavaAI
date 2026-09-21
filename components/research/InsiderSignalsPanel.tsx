import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { getInsiderSignals } from '@/lib/actions/market-signals.actions';

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-dashed border-gray-800 p-4 text-sm text-gray-500">{children}</p>;
}

/** Señales insider (Form 4, SEC). Server component: nunca rompe la página. */
export async function InsiderSignalsPanel({ ticker }: { ticker: string }) {
  const data = await getInsiderSignals(ticker);
  return (
    <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-gray-100">Insider signals</h2>
        <Badge variant="outline">{data.status}</Badge>
      </div>
      <div className="mt-4">
        {data.signals.length ? (
          <ul className="space-y-2">
            {data.signals.slice(0, 5).map((signal, index) => (
              <li className="rounded-lg border border-gray-800 p-3 text-sm text-gray-300" key={index}>
                <span className="font-medium text-gray-100">
                  {String(signal.insider ?? signal.transaction_type ?? signal.transaction ?? 'Filing')}
                </span>
                <span className="ml-2 text-gray-500">
                  {[signal.shares != null ? `${signal.shares} sh` : null, signal.filed_at ?? null]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>
            {data.status === 'unavailable'
              ? 'No insider data (non-US filer or SEC unreachable).'
              : 'No recent insider transactions.'}
          </Empty>
        )}
      </div>
      <Link className="mt-3 inline-block text-xs text-teal-300 hover:text-teal-200" href="/research/news">
        View news flow
      </Link>
    </section>
  );
}

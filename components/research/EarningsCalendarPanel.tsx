import { Badge } from '@/components/ui/badge';
import { getEarningsCalendar } from '@/lib/actions/market-signals.actions';

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-dashed border-gray-800 p-4 text-sm text-gray-500">{children}</p>;
}

/** Próximos earnings (calendario NASDAQ, 7 días). Server component seguro. */
export async function EarningsCalendarPanel({ highlightTicker }: { highlightTicker?: string }) {
  const data = await getEarningsCalendar();
  const normalized = highlightTicker?.toUpperCase();
  const events = normalized
    ? [...data.events].sort((a, b) => (a.symbol === normalized ? -1 : b.symbol === normalized ? 1 : 0))
    : data.events;
  return (
    <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-gray-100">Upcoming earnings</h2>
        <Badge variant="outline">{data.status}</Badge>
      </div>
      <div className="mt-4">
        {events.length ? (
          <ul className="space-y-2">
            {events.slice(0, 8).map((event, index) => (
              <li
                className={`rounded-lg border p-3 text-sm text-gray-300 ${
                  normalized && event.symbol === normalized ? 'border-teal-700 bg-teal-950/30' : 'border-gray-800'
                }`}
                key={`${event.symbol ?? 'event'}-${index}`}
              >
                <span className="font-medium text-gray-100">{event.symbol ?? event.name ?? 'Unknown'}</span>
                <span className="ml-2 text-gray-500">
                  {[event.date ?? null, event.time ?? null].filter(Boolean).join(' · ') || 'date TBA'}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>
            {data.status === 'unavailable' ? 'Earnings calendar unreachable.' : 'No earnings in the next 7 days.'}
          </Empty>
        )}
      </div>
    </section>
  );
}

import { AlertTriangle, ArrowLeft, Minus, TrendingDown, TrendingUp } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { analyzeManualNews, getResearchNews } from '@/lib/actions/research.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

async function submitAnalyzeNews(formData: FormData): Promise<void> {
  'use server';
  await analyzeManualNews(formData);
}

function Stat({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: string;
  tone?: 'default' | 'good' | 'warn' | 'bad';
}) {
  const toneClass = {
    default: 'text-gray-100',
    good: 'text-teal-300',
    warn: 'text-amber-300',
    bad: 'text-red-300',
  }[tone];

  return (
    <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
      <div className="text-xs font-semibold uppercase text-gray-500">{label}</div>
      <div className={`mt-2 text-2xl font-semibold ${toneClass}`}>{value}</div>
    </div>
  );
}

export default async function ResearchNewsPage() {
  const events = await getResearchNews();
  const requireUpdate = events.filter((e) => e.requires_update).length;
  const highMateriality = events.filter((e) => e.materiality_score >= 7).length;

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="flex flex-col gap-4 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <Button asChild className="mb-4" size="sm" variant="ghost">
            <Link href="/research">
              <ArrowLeft className="h-4 w-4" />
              Research
            </Link>
          </Button>
          <p className="text-sm font-semibold uppercase text-teal-300">Market Intelligence</p>
          <h1 className="mt-1 text-3xl font-bold text-gray-100">News Events</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Eventos de noticias clasificados por materialidad e impacto sobre posiciones de cartera.
          </p>
        </div>
        <div className="rounded-lg border border-gray-800 bg-[#111111] px-4 py-3 text-sm text-gray-300">
          {events.length} eventos
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <Stat label="Total Events" value={String(events.length)} />
        <Stat label="Require Update" value={String(requireUpdate)} tone={requireUpdate > 0 ? 'bad' : 'good'} />
        <Stat label="High Materiality" value={String(highMateriality)} tone={highMateriality > 0 ? 'warn' : 'good'} />
      </section>

      <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
        <div className="mb-4 flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Event Feed</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="text-xs uppercase text-gray-500">
              <tr>
                <th className="border-b border-gray-800 py-2">Ticker</th>
                <th className="border-b border-gray-800 py-2">Date</th>
                <th className="border-b border-gray-800 py-2">Title</th>
                <th className="border-b border-gray-800 py-2">Source</th>
                <th className="border-b border-gray-800 py-2">Type</th>
                <th className="border-b border-gray-800 py-2 text-center">Materiality</th>
                <th className="border-b border-gray-800 py-2 text-center">Direction</th>
                <th className="border-b border-gray-800 py-2 text-center">Update?</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => {
                const materialityColor =
                  event.materiality_score >= 7
                    ? 'text-red-400'
                    : event.materiality_score >= 4
                      ? 'text-amber-400'
                      : 'text-gray-500';

                const dir = event.impact_direction.toLowerCase();
                const DirectionIcon =
                  dir === 'up' || dir === 'positive'
                    ? TrendingUp
                    : dir === 'down' || dir === 'negative'
                      ? TrendingDown
                      : Minus;

                return (
                  <tr key={event.id} className="border-b border-gray-900 last:border-0">
                    <td className="py-3 font-semibold">
                      {event.ticker ? (
                        <Link
                          className="text-teal-300 hover:text-teal-200"
                          href={`/research/${event.ticker}`}
                        >
                          {event.ticker}
                        </Link>
                      ) : (
                        <span className="text-gray-500">—</span>
                      )}
                    </td>
                    <td className="py-3 text-gray-400">{event.date.split('T')[0]}</td>
                    <td className="py-3 max-w-[280px] truncate text-gray-300">{event.title}</td>
                    <td className="py-3 text-gray-400">{event.source}</td>
                    <td className="py-3 text-gray-400">{event.event_type}</td>
                    <td className="py-3 text-center">
                      <span className={`font-semibold ${materialityColor}`}>
                        {event.materiality_score}
                      </span>
                    </td>
                    <td className="py-3 text-center">
                      <DirectionIcon className="inline-block h-4 w-4 text-gray-400" />
                    </td>
                    <td className="py-3 text-center">
                      {event.requires_update ? (
                        <span className="rounded-full bg-red-950/60 px-2 py-0.5 text-xs font-semibold text-red-400">
                          urgent
                        </span>
                      ) : (
                        <span className="rounded-full bg-gray-900 px-2 py-0.5 text-xs text-gray-500">
                          ok
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {!events.length ? (
                <tr>
                  <td className="py-4 text-gray-500" colSpan={8}>
                    Sin eventos de noticias todavia.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
        <div className="mb-4 flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Analyze Manual News</h2>
        </div>
        <form action={submitAnalyzeNews} className="grid gap-3">
          <div className="grid gap-2">
            <label className="text-sm font-semibold text-gray-400" htmlFor="text">
              News text
            </label>
            <Textarea
              className="min-h-[160px] border-gray-800 bg-black/30 text-gray-200 focus-visible:ring-teal-500"
              id="text"
              name="text"
              placeholder="Paste the news article, press release or IR note here..."
              required
            />
          </div>
          <div className="grid gap-2 sm:grid-cols-[160px_1fr] sm:items-center">
            <label className="text-sm font-semibold text-gray-400" htmlFor="source">
              Source
            </label>
            <Input id="source" name="source" placeholder="Bloomberg, FT, IR..." />
          </div>
          <Button className="w-full sm:w-fit" type="submit">
            Analyze News
          </Button>
        </form>
      </section>
    </main>
  );
}

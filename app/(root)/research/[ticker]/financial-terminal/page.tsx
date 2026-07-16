import Link from 'next/link';
import { ArrowLeft, Database, SlidersHorizontal } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { getFinancialTerminal } from '@/lib/actions/research-tools.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

function value(raw: string | number | null, unit: string) {
  if (raw === null) return 'n/a';
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return String(raw);
  if (unit === 'decimal') return `${(parsed * 100).toFixed(1)}%`;
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(parsed);
}

export default async function FinancialTerminalPage({ params, searchParams }: { params: Promise<{ ticker: string }>; searchParams: Promise<{ metrics?: string; years?: string; periodicity?: string }> }) {
  const [{ ticker: rawTicker }, query] = await Promise.all([params, searchParams]);
  const ticker = rawTicker.toUpperCase();
  const years = Math.max(1, Math.min(20, Number(query.years) || 10));
  const periodicity = ['all', 'annual', 'quarterly'].includes(query.periodicity ?? '') ? query.periodicity! : 'annual';
  const terminal = await getFinancialTerminal(ticker, { metrics: query.metrics, years, periodicity });
  return <main className="mx-auto flex max-w-[1600px] flex-col gap-6">
    <header className="border-b border-gray-800 pb-5"><Button asChild className="mb-4" size="sm" variant="ghost"><Link href={`/research/${ticker}`}><ArrowLeft className="h-4 w-4" />{ticker} workspace</Link></Button><p className="text-sm font-semibold uppercase text-teal-300">Source-aware financials</p><h1 className="mt-1 text-3xl font-bold text-gray-100">Financial Terminal</h1><p className="mt-2 text-sm text-gray-400">Reported, normalized and calculated metrics with definitions, formulas, confidence and source trace.</p></header>
    <section className="grid gap-4 sm:grid-cols-4">{[['Coverage', `${terminal.coverage.percent.toFixed(0)}%`], ['Available', `${terminal.coverage.available}/${terminal.coverage.requested}`], ['Range', `${terminal.range.from_fiscal_year}–${terminal.range.to_fiscal_year}`], ['Periodicity', terminal.periodicity]].map(([label, data]) => <div className="rounded-xl border border-gray-800 bg-[#101010] p-4" key={label}><div className="text-xs font-semibold uppercase text-gray-500">{label}</div><div className="mt-2 text-xl font-semibold text-gray-100">{data}</div></div>)}</section>
    <form className="rounded-xl border border-gray-800 bg-[#101010] p-4" method="get"><div className="mb-3 flex items-center gap-2"><SlidersHorizontal className="h-4 w-4 text-teal-300" /><h2 className="font-semibold text-gray-200">Terminal controls</h2></div><div className="grid gap-3 md:grid-cols-[1fr_120px_160px_auto]"><Input defaultValue={query.metrics} name="metrics" placeholder="Metrics, comma separated (blank = defaults)" /><Input defaultValue={years} max="20" min="1" name="years" type="number" /><select className="h-9 rounded-md border border-gray-800 bg-black px-3 text-sm text-gray-200" defaultValue={periodicity} name="periodicity"><option value="annual">Annual</option><option value="quarterly">Quarterly</option><option value="all">All periods</option></select><Button type="submit">Apply</Button></div></form>
    <section className="grid gap-5">{terminal.metrics.map((metric) => <article className="rounded-xl border border-gray-800 bg-[#101010] p-5" key={metric.metric}><div className="flex flex-col gap-3 md:flex-row md:items-start"><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-lg font-semibold text-gray-100">{metric.metric.replaceAll('_', ' ')}</h2><Badge className={metric.status === 'available' ? 'border-teal-800 text-teal-300' : 'border-amber-900 text-amber-300'} variant="outline">{metric.status}</Badge></div><p className="mt-2 text-sm text-gray-400">{metric.definition}</p>{metric.canonical_formula ? <code className="mt-2 block text-xs text-teal-300">{metric.canonical_formula} · {metric.definition_version}</code> : null}</div><div className="flex flex-wrap gap-2 md:ml-auto"><Badge variant="outline">{metric.periods} periods</Badge>{metric.segments.map((segment) => <Badge key={segment} variant="outline">{segment}</Badge>)}</div></div>{metric.series.length ? <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[1000px] text-left text-sm"><thead className="text-xs uppercase text-gray-500"><tr><th className="border-b border-gray-800 py-2">Period</th><th className="border-b border-gray-800 py-2 text-right">Value</th><th className="border-b border-gray-800 py-2">Status</th><th className="border-b border-gray-800 py-2">Segment</th><th className="border-b border-gray-800 py-2 text-right">Confidence</th><th className="border-b border-gray-800 py-2">Source</th></tr></thead><tbody>{metric.series.map((point) => <tr className="border-b border-gray-900" key={`${point.id}-${point.period}-${point.status}`}><td className="py-3 font-medium text-gray-300">{point.period}</td><td className="py-3 text-right font-semibold text-gray-100">{value(point.value, point.unit)} <span className="text-xs font-normal text-gray-500">{point.unit}</span></td><td className="py-3"><Badge variant="outline">{point.status}</Badge></td><td className="py-3 text-gray-400">{point.segment}</td><td className="py-3 text-right text-gray-400">{(Number(point.confidence) * 100).toFixed(0)}%</td><td className="py-3 text-gray-500"><div className="flex items-center gap-1"><Database className="h-3 w-3" />{point.source.title ?? point.source.type}</div></td></tr>)}</tbody></table></div> : <p className="mt-4 rounded-lg border border-dashed border-gray-800 p-4 text-sm text-gray-500">No observations for this metric and period filter.</p>}</article>)}</section>
  </main>;
}

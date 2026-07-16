import Link from 'next/link';
import { Calculator, Filter, Play, Save } from 'lucide-react';

import { MutationForm } from '@/components/forms/MutationForm';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  createCustomMetric,
  createSavedScreen,
  getScreenerWorkspace,
  runAdHocScreen,
  type ScreenCriterion,
  type ScreenResult,
} from '@/lib/actions/research-tools.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type PageProps = { searchParams: Promise<{ left?: string; operator?: string; right?: string; ranking?: string; direction?: string }> };
const operators: ScreenCriterion['operator'][] = ['>', '>=', '<', '<=', '==', '!='];

function Results({ result }: { result: ScreenResult }) {
  const newMatches = new Set(result.new_match_company_ids ?? []);
  return (
    <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center"><div><h2 className="text-lg font-semibold text-gray-100">Screen results</h2><p className="text-sm text-gray-500">{result.match_count} matches across {result.company_count} companies</p></div>{result.ranking_formula ? <Badge className="md:ml-auto" variant="outline">rank: {result.ranking_formula} · {result.ranking_direction}</Badge> : null}</div>
      <div className="overflow-x-auto"><table className="w-full min-w-[980px] text-left text-sm"><thead className="text-xs uppercase text-gray-500"><tr><th className="border-b border-gray-800 py-2">Company</th><th className="border-b border-gray-800 py-2">Match</th><th className="border-b border-gray-800 py-2 text-right">Rank</th><th className="border-b border-gray-800 py-2 text-right">Coverage</th><th className="border-b border-gray-800 py-2 text-right">Confidence</th><th className="border-b border-gray-800 py-2">Latest data</th><th className="border-b border-gray-800 py-2">Missing</th></tr></thead><tbody>
        {result.results.map((row) => <tr className="border-b border-gray-900" key={row.company_id}><td className="py-3"><Link className="font-semibold text-teal-300 hover:text-teal-200" href={`/research/${row.ticker}`}>{row.ticker}</Link><div className="text-xs text-gray-500">{row.name}</div></td><td className="py-3"><div className="flex gap-2"><Badge className={row.matched ? 'border-teal-800 text-teal-300' : 'border-gray-700 text-gray-400'} variant="outline">{row.matched ? 'match' : 'no match'}</Badge>{newMatches.has(row.company_id) ? <Badge>new</Badge> : null}</div></td><td className="py-3 text-right text-gray-300">{row.rank_value ?? 'n/a'}</td><td className="py-3 text-right text-gray-300">{row.coverage_percent.toFixed(0)}%</td><td className="py-3 text-right text-gray-300">{(Number(row.confidence) * 100).toFixed(0)}%</td><td className="py-3 text-gray-500">{row.latest_data_at ?? 'n/a'}</td><td className="py-3 text-amber-300">{row.missing_fields.join(', ') || '—'}</td></tr>)}
      </tbody></table></div>
    </section>
  );
}

export default async function ScreenersPage({ searchParams }: PageProps) {
  const query = await searchParams;
  const operator = operators.includes(query.operator as ScreenCriterion['operator']) ? query.operator as ScreenCriterion['operator'] : '>=';
  const [{ metrics, screens }, result] = await Promise.all([
    getScreenerWorkspace(),
    runAdHocScreen({
      left: query.left ?? '',
      operator,
      right: query.right ?? '',
      rankingFormula: query.ranking,
      rankingDirection: query.direction === 'asc' ? 'asc' : 'desc',
    }),
  ]);

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="border-b border-gray-800 pb-5"><p className="text-sm font-semibold uppercase text-teal-300">Company discovery</p><h1 className="mt-1 text-3xl font-bold text-gray-100">Screeners</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">Build safe formulas, evaluate coverage and confidence, save screens and identify new matches.</p></header>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <form className="rounded-xl border border-gray-800 bg-[#101010] p-5" method="get">
          <div className="mb-4 flex items-center gap-2"><Filter className="h-5 w-5 text-teal-300" /><h2 className="font-semibold text-gray-100">Run an ad-hoc screen</h2></div>
          <div className="grid gap-3 md:grid-cols-[1fr_110px_1fr]"><Input defaultValue={query.left} name="left" placeholder="roic - wacc" required /><select className="h-9 rounded-md border border-gray-800 bg-black px-3 text-sm text-gray-200" defaultValue={operator} name="operator">{operators.map((item) => <option key={item}>{item}</option>)}</select><Input defaultValue={query.right} name="right" placeholder="0" required /></div>
          <div className="mt-3 grid gap-3 md:grid-cols-[1fr_180px_auto]"><Input defaultValue={query.ranking} name="ranking" placeholder="Ranking formula (optional)" /><select className="h-9 rounded-md border border-gray-800 bg-black px-3 text-sm text-gray-200" defaultValue={query.direction ?? 'desc'} name="direction"><option value="desc">Highest first</option><option value="asc">Lowest first</option></select><Button type="submit"><Play className="h-4 w-4" />Run</Button></div>
          <p className="mt-3 text-xs text-gray-500">Allowed: numbers, metric names, arithmetic, min, max and abs. No arbitrary code is executed.</p>
        </form>

        <MutationForm action={createCustomMetric} className="rounded-xl border border-gray-800 bg-[#101010] p-5" resetOnSuccess successMessage="Custom metric saved">
          <div className="mb-4 flex items-center gap-2"><Calculator className="h-5 w-5 text-teal-300" /><h2 className="font-semibold text-gray-100">Custom metric</h2></div>
          <div className="grid gap-3 sm:grid-cols-2"><Input name="metric_key" placeholder="roic_spread" required /><Input name="name" placeholder="ROIC spread" required /><Input className="sm:col-span-2" name="formula" placeholder="roic - wacc" required /><Input name="unit" defaultValue="decimal" /><Input name="description" placeholder="Definition" /><Button className="w-fit" type="submit">Save metric</Button></div>
        </MutationForm>
      </section>

      {result ? <Results result={result} /> : null}

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <MutationForm action={createSavedScreen} className="rounded-xl border border-gray-800 bg-[#101010] p-5" resetOnSuccess successMessage="Screen saved">
          <div className="mb-4 flex items-center gap-2"><Save className="h-5 w-5 text-teal-300" /><h2 className="font-semibold text-gray-100">Visual screen builder</h2></div>
          <div className="grid gap-3 sm:grid-cols-2"><Input name="name" placeholder="Quality at a reasonable price" required /><Input name="description" placeholder="Purpose and universe" /></div>
          {([['', true], ['_2', false], ['_3', false]] as const).map(([suffix, required]) => <div className="mt-3 grid gap-3 md:grid-cols-[1fr_110px_1fr]" key={suffix || 'one'}><Input name={`left${suffix}`} placeholder={suffix ? 'Optional formula' : 'roic'} required={required} /><select className="h-9 rounded-md border border-gray-800 bg-black px-3 text-sm text-gray-200" name={`operator${suffix}`} defaultValue={'>='}>{operators.map((item) => <option key={item}>{item}</option>)}</select><Input name={`right${suffix}`} placeholder={suffix ? 'Optional threshold' : 'wacc'} required={required} /></div>)}
          <div className="mt-3 grid gap-3 sm:grid-cols-2"><Input name="ranking_formula" placeholder="free_cash_flow / market_cap" /><select className="h-9 rounded-md border border-gray-800 bg-black px-3 text-sm text-gray-200" name="ranking_direction" defaultValue="desc"><option value="desc">Highest first</option><option value="asc">Lowest first</option></select></div>
          <label className="mt-4 flex items-center gap-2 text-sm text-gray-300"><input defaultChecked name="alerts_enabled" type="checkbox" />Alert on new matches</label>
          <Button className="mt-4" type="submit"><Save className="h-4 w-4" />Save screen</Button>
        </MutationForm>

        <section className="rounded-xl border border-gray-800 bg-[#101010] p-5"><h2 className="font-semibold text-gray-100">Saved screens</h2><div className="mt-4 grid gap-3">{screens.map((screen) => <article className="rounded-lg border border-gray-800 bg-black/30 p-4" key={screen.id}><div className="flex items-start gap-3"><div><h3 className="font-semibold text-gray-200">{screen.name}</h3><p className="mt-1 text-xs text-gray-500">{screen.criteria.length} criteria · {screen.alerts_enabled ? 'alerts on' : 'alerts off'} · last {screen.last_run_at ?? 'never'}</p></div><Button asChild className="ml-auto" size="sm"><Link href={`/screeners/${screen.id}`}><Play className="h-4 w-4" />Run</Link></Button></div>{screen.description ? <p className="mt-3 text-sm text-gray-400">{screen.description}</p> : null}</article>)}{!screens.length ? <p className="text-sm text-gray-500">No saved screens yet.</p> : null}</div></section>
      </section>

      <section className="rounded-xl border border-gray-800 bg-[#101010] p-5"><h2 className="font-semibold text-gray-100">Active custom metrics</h2><div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{metrics.map((metric) => <article className="rounded-lg border border-gray-800 bg-black/30 p-4" key={metric.id}><div className="flex items-center justify-between gap-3"><span className="font-semibold text-gray-200">{metric.name}</span><Badge variant="outline">v{metric.version}</Badge></div><code className="mt-3 block text-sm text-teal-300">{metric.metric_key} = {metric.formula}</code><p className="mt-2 text-xs text-gray-500">{metric.unit} · {metric.description || 'No description'}</p></article>)}{!metrics.length ? <p className="text-sm text-gray-500">No custom metrics yet.</p> : null}</div></section>
    </main>
  );
}

import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { runSavedScreen } from '@/lib/actions/research-tools.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function SavedScreenResultsPage({ params }: { params: Promise<{ screenId: string }> }) {
  const { screenId } = await params;
  const result = await runSavedScreen(Number(screenId));
  const newMatches = new Set(result.new_match_company_ids ?? []);
  return <main className="mx-auto flex max-w-7xl flex-col gap-6"><header className="border-b border-gray-800 pb-5"><Button asChild className="mb-4" size="sm" variant="ghost"><Link href="/screeners"><ArrowLeft className="h-4 w-4" />Screeners</Link></Button><p className="text-sm font-semibold uppercase text-teal-300">Saved screen</p><h1 className="mt-1 text-3xl font-bold text-gray-100">Results</h1><p className="mt-2 text-sm text-gray-400">{result.match_count} matches across {result.company_count} companies. This run records match history and emits configured new-match alerts.</p></header><section className="grid gap-3">{result.results.map((row) => <article className={`rounded-xl border p-4 ${row.matched ? 'border-teal-900/70 bg-teal-950/10' : 'border-gray-800 bg-[#101010]'}`} key={row.company_id}><div className="flex flex-col gap-3 md:flex-row md:items-center"><div><Link className="text-lg font-semibold text-teal-300" href={`/research/${row.ticker}`}>{row.ticker}</Link><p className="text-sm text-gray-500">{row.name}</p></div><div className="flex flex-wrap gap-2 md:ml-auto"><Badge variant="outline">{row.matched ? 'match' : 'no match'}</Badge>{newMatches.has(row.company_id) ? <Badge>new match</Badge> : null}<Badge variant="outline">rank {row.rank_value ?? 'n/a'}</Badge><Badge variant="outline">coverage {row.coverage_percent.toFixed(0)}%</Badge><Badge variant="outline">confidence {(Number(row.confidence) * 100).toFixed(0)}%</Badge></div></div>{row.missing_fields.length ? <p className="mt-3 text-sm text-amber-300">Missing: {row.missing_fields.join(', ')}</p> : null}<div className="mt-3 grid gap-2 md:grid-cols-2">{row.criteria.map((criterion, index) => <div className="rounded-md border border-gray-800 p-3 text-xs" key={index}><span className={criterion.passed ? 'text-teal-300' : 'text-red-300'}>{criterion.passed ? 'PASS' : 'FAIL'}</span><span className="ml-2 text-gray-300">{criterion.left} {criterion.operator} {criterion.right}</span></div>)}</div></article>)}</section></main>;
}

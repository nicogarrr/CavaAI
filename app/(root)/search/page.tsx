import Link from 'next/link';
import { BookOpen, Filter, Search as SearchIcon } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { searchResearchLibrary } from '@/lib/actions/research-tools.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type PageProps = {
  searchParams: Promise<{
    q?: string;
    ticker?: string;
    entity_types?: string;
    source_types?: string;
    statuses?: string;
    collection_id?: string;
    date_from?: string;
    date_to?: string;
    vector?: string;
  }>;
};

export default async function UniversalSearchPage({ searchParams }: PageProps) {
  const query = await searchParams;
  const response = await searchResearchLibrary({
    query: query.q ?? '',
    ticker: query.ticker,
    entityTypes: query.entity_types,
    sourceTypes: query.source_types,
    statuses: query.statuses,
    collectionId: Number(query.collection_id) || undefined,
    dateFrom: query.date_from,
    dateTo: query.date_to,
    includeVector: query.vector !== 'false',
  });
  const searched = Boolean(query.q?.trim());

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="flex flex-col gap-4 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase text-teal-300">Research retrieval</p>
          <h1 className="mt-1 text-3xl font-bold text-gray-100">Universal Search</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">Search company evidence, facts, claims, thesis sections, decisions, lessons and the investment library in one ranked result set.</p>
        </div>
        <Button asChild variant="outline"><Link href="/knowledge"><BookOpen className="h-4 w-4" />Knowledge Library</Link></Button>
      </header>

      <form className="rounded-xl border border-gray-800 bg-[#101010] p-5" method="get">
        <div className="flex gap-3">
          <Input autoFocus className="h-11 text-base" defaultValue={query.q} name="q" placeholder="Search across all research..." required />
          <Button className="h-11" type="submit"><SearchIcon className="h-4 w-4" />Search</Button>
        </div>
        <details className="mt-4">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-gray-400"><Filter className="h-4 w-4" />Advanced filters</summary>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Input defaultValue={query.ticker} name="ticker" placeholder="Ticker" />
            <Input defaultValue={query.entity_types} name="entity_types" placeholder="Entity types, comma separated" />
            <Input defaultValue={query.source_types} name="source_types" placeholder="Source types, comma separated" />
            <Input defaultValue={query.statuses} name="statuses" placeholder="Statuses, comma separated" />
            <Input defaultValue={query.collection_id} min="1" name="collection_id" placeholder="Collection ID" type="number" />
            <Input defaultValue={query.date_from} name="date_from" type="date" />
            <Input defaultValue={query.date_to} name="date_to" type="date" />
            <select className="h-9 rounded-md border border-gray-800 bg-black px-3 text-sm text-gray-200" defaultValue={query.vector ?? 'true'} name="vector"><option value="true">Lexical + vector</option><option value="false">Lexical only</option></select>
          </div>
        </details>
      </form>

      {searched ? (
        <section className="grid gap-4">
          <div className="flex flex-col gap-3 rounded-xl border border-gray-800 bg-[#101010] p-4 md:flex-row md:items-center">
            <div><div className="text-sm font-semibold text-gray-100">{response.total} results for “{response.query}”</div><div className="mt-1 text-xs text-gray-500">Ranked with lexical/vector fusion, source hierarchy and canonical-status signals.</div></div>
            <div className="flex flex-wrap gap-2 md:ml-auto">
              {Object.entries(response.retrieval).filter(([, value]) => typeof value === 'string').map(([key, value]) => <Badge key={key} variant="outline">{key}: {String(value)}</Badge>)}
            </div>
          </div>

          {response.results.map((result, index) => (
            <article className="rounded-xl border border-gray-800 bg-[#101010] p-5" key={`${result.entity_type}-${result.entity_id}`}>
              <div className="flex flex-col gap-3 md:flex-row md:items-start">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-950 text-sm font-semibold text-teal-300">{index + 1}</div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2"><Badge>{result.entity_type}</Badge>{result.ticker ? <Badge variant="outline">{result.ticker}</Badge> : null}<Badge variant="outline">{result.source_tier}</Badge><Badge variant="outline">{result.status}</Badge></div>
                  <h2 className="mt-3 text-lg font-semibold text-gray-100">{result.title}</h2>
                  <p className="mt-2 line-clamp-5 whitespace-pre-wrap text-sm leading-6 text-gray-300">{result.text}</p>
                  <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-gray-500"><span>{result.citation}</span><span>{result.collection ?? result.source_type}</span><span>{result.as_of ?? 'date unavailable'}</span><span>trust {(result.source_trust * 100).toFixed(0)}%</span><span>rank {result.scores.reranker.toFixed(4)}</span></div>
                </div>
              </div>
            </article>
          ))}
          {!response.results.length ? <div className="rounded-xl border border-dashed border-gray-800 p-8 text-center text-sm text-gray-500">No evidence matched the query and filters.</div> : null}
        </section>
      ) : (
        <section className="rounded-xl border border-dashed border-gray-800 p-10 text-center"><SearchIcon className="mx-auto h-8 w-8 text-gray-600" /><h2 className="mt-3 font-semibold text-gray-300">Start with a company, concept, KPI or prior decision</h2><p className="mt-2 text-sm text-gray-500">Examples: dilution risk, incremental ROIC, management promises, selling too early.</p></section>
      )}
    </main>
  );
}

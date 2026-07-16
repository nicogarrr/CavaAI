import Link from 'next/link';
import { BookOpen, Check, FileSearch, Library, Sparkles, UploadCloud, X } from 'lucide-react';

import { MutationForm } from '@/components/forms/MutationForm';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  createKnowledgeCollection,
  decideKnowledgePrinciple,
  extractKnowledgePrinciples,
  getKnowledgeDocumentChunks,
  getKnowledgeLibrary,
  installKnowledgeDefaults,
  mergeKnowledgePrinciple,
  reviseKnowledgePrinciple,
  uploadKnowledgeDocument,
} from '@/lib/actions/research-tools.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type PageProps = { searchParams: Promise<{ document?: string; status?: string }> };

function statusTone(status: string) {
  if (status === 'approved' || status === 'ready') return 'border-teal-800 text-teal-300';
  if (status === 'rejected') return 'border-red-900 text-red-300';
  return 'border-amber-900 text-amber-300';
}

export default async function KnowledgeLibraryPage({ searchParams }: PageProps) {
  const query = await searchParams;
  const selectedDocumentId = Number(query.document) || null;
  const [{ collections, documents, principles, jobs }, chunks] = await Promise.all([
    getKnowledgeLibrary(),
    getKnowledgeDocumentChunks(selectedDocumentId),
  ]);
  const visiblePrinciples = query.status
    ? principles.filter((principle) => principle.status === query.status)
    : principles;
  const collectionNames = new Map(collections.map((collection) => [collection.id, collection.name]));
  const documentNames = new Map(documents.map((document) => [document.id, document.title]));
  const selectedDocument = documents.find((document) => document.id === selectedDocumentId);
  const activeJobs = jobs.filter((job) => job.status === 'queued' || job.status === 'running');
  const latestJobByDocument = new Map<number, (typeof jobs)[number]>();
  jobs.forEach((job) => {
    if (job.entity_id && !latestJobByDocument.has(job.entity_id)) {
      latestJobByDocument.set(job.entity_id, job);
    }
  });

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="flex flex-col gap-4 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase text-teal-300">Investment knowledge</p>
          <h1 className="mt-1 text-3xl font-bold text-gray-100">Knowledge Library</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Books, letters and case studies kept separate from company evidence, with traceable human-approved principles.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline"><Link href="/search"><FileSearch className="h-4 w-4" />Search all</Link></Button>
          <Button asChild variant="outline"><Link href="/knowledge-graph"><Library className="h-4 w-4" />Knowledge Graph</Link></Button>
          <MutationForm action={installKnowledgeDefaults} successMessage="Default collections ready">
            <Button type="submit"><Library className="h-4 w-4" />Install defaults</Button>
          </MutationForm>
        </div>
      </header>

      <section className="grid gap-4 sm:grid-cols-3">
        {[
          ['Collections', collections.length],
          ['Documents', documents.length],
          ['Pending approval', principles.filter((item) => item.status === 'proposed').length],
        ].map(([label, value]) => (
          <div className="rounded-xl border border-gray-800 bg-[#101010] p-4" key={label}>
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</div>
            <div className="mt-2 text-2xl font-semibold text-gray-100">{value}</div>
          </div>
        ))}
      </section>

      {activeJobs.length ? (
        <section className="rounded-xl border border-amber-900/60 bg-amber-950/10 p-4 text-sm text-amber-100">
          <div className="font-semibold">Background extraction in progress</div>
          <div className="mt-2 grid gap-1 text-amber-200/80">
            {activeJobs.map((job) => (
              <div key={job.id}>Job #{job.id} · {documentNames.get(job.entity_id ?? -1) ?? `document ${job.entity_id}`} · {job.status}{job.progress_total ? ` · batch ${job.progress_current}/${job.progress_total}` : ''}</div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-2">
        <MutationForm action={createKnowledgeCollection} className="rounded-xl border border-gray-800 bg-[#101010] p-5" resetOnSuccess successMessage="Collection created">
          <div className="mb-4 flex items-center gap-2"><Library className="h-5 w-5 text-teal-300" /><h2 className="font-semibold text-gray-100">New collection</h2></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input name="name" placeholder="Quality compounders" required />
            <Input name="collection_type" defaultValue="custom" placeholder="Collection type" required />
            <Textarea className="sm:col-span-2" name="description" placeholder="Scope and intended use" />
            <Button className="w-fit" type="submit">Create collection</Button>
          </div>
        </MutationForm>

        <MutationForm action={uploadKnowledgeDocument} className="rounded-xl border border-gray-800 bg-[#101010] p-5" resetOnSuccess successMessage="Document ingested">
          <div className="mb-4 flex items-center gap-2"><UploadCloud className="h-5 w-5 text-teal-300" /><h2 className="font-semibold text-gray-100">Upload knowledge</h2></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input name="title" placeholder="Document title" required />
            <select className="h-9 rounded-md border border-gray-800 bg-black px-3 text-sm text-gray-200" name="collection_id" defaultValue="">
              <option value="">Unassigned collection</option>
              {collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}
            </select>
            <Input name="author" placeholder="Author" />
            <Input name="document_type" defaultValue="book" placeholder="book, letter, paper" required />
            <Input name="publication_date" type="date" />
            <Input name="language" defaultValue="en" placeholder="Language" />
            <Input className="sm:col-span-2" name="source_url" placeholder="Source URL (optional)" type="url" />
            <Input accept=".pdf,.docx,.txt,.md,.html,.xlsx,.csv" className="sm:col-span-2" name="file" required type="file" />
            <Button className="w-fit" type="submit"><UploadCloud className="h-4 w-4" />Upload</Button>
          </div>
        </MutationForm>
      </section>

      <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
        <div className="mb-4 flex items-center gap-2"><BookOpen className="h-5 w-5 text-teal-300" /><h2 className="text-lg font-semibold text-gray-100">Documents</h2></div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="text-xs uppercase text-gray-500"><tr><th className="border-b border-gray-800 py-2">Document</th><th className="border-b border-gray-800 py-2">Collection</th><th className="border-b border-gray-800 py-2">Type</th><th className="border-b border-gray-800 py-2">Parser</th><th className="border-b border-gray-800 py-2">Status</th><th className="border-b border-gray-800 py-2 text-right">Actions</th></tr></thead>
            <tbody>
              {documents.map((document) => {
                const job = latestJobByDocument.get(document.id);
                const busy = job?.status === 'queued' || job?.status === 'running';
                return (
                <tr className="border-b border-gray-900" key={document.id}>
                  <td className="py-3"><div className="font-medium text-gray-200">{document.title}</div><div className="text-xs text-gray-500">{document.author ?? 'Unknown author'} · {document.publication_date ?? 'undated'}</div></td>
                  <td className="py-3 text-gray-400">{document.collection_id ? collectionNames.get(document.collection_id) : 'Unassigned'}</td>
                  <td className="py-3 text-gray-400">{document.document_type}</td>
                  <td className="py-3 text-gray-500">{String(document.metadata.parser ?? 'unknown')}</td>
                  <td className="py-3"><Badge className={statusTone(document.status)} variant="outline">{document.status}</Badge></td>
                  <td className="py-3"><div className="flex justify-end gap-2"><Button asChild size="sm" variant="outline"><Link href={`/knowledge?document=${document.id}`}>Chunks</Link></Button><MutationForm action={extractKnowledgePrinciples.bind(null, document.id)} successMessage="Extraction queued"><Button disabled={busy} size="sm" type="submit"><Sparkles className="h-4 w-4" />{busy ? job?.status : 'Extract'}</Button></MutationForm></div>{job?.status === 'failed' ? <div className="mt-1 max-w-xs text-right text-xs text-red-300">{job.error}</div> : null}</td>
                </tr>
                );
              })}
              {!documents.length ? <tr><td className="py-5 text-gray-500" colSpan={6}>No knowledge documents yet.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>

      {selectedDocument ? (
        <section className="rounded-xl border border-teal-900/50 bg-[#101010] p-5">
          <div className="mb-4 flex items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase text-teal-300">Chunk browser</p><h2 className="text-lg font-semibold text-gray-100">{selectedDocument.title}</h2></div><Button asChild size="sm" variant="ghost"><Link href="/knowledge">Close</Link></Button></div>
          <div className="grid max-h-[620px] gap-3 overflow-y-auto pr-2">
            {chunks.map((chunk) => <article className="rounded-lg border border-gray-800 bg-black/30 p-4" key={chunk.id}><div className="mb-2 flex justify-between text-xs text-gray-500"><span>Chunk {chunk.chunk_index + 1}</span><span>page {chunk.page_number ?? 'n/a'} · {chunk.token_count} tokens</span></div><p className="whitespace-pre-wrap text-sm leading-6 text-gray-300">{chunk.content}</p></article>)}
            {!chunks.length ? <p className="text-sm text-gray-500">This document has no chunks.</p> : null}
          </div>
        </section>
      ) : null}

      <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center"><div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-teal-300" /><h2 className="text-lg font-semibold text-gray-100">Investment principles</h2></div><div className="flex flex-wrap gap-2 md:ml-auto">{['', 'proposed', 'approved', 'rejected', 'merged', 'superseded'].map((status) => <Button asChild key={status || 'all'} size="sm" variant={(query.status ?? '') === status ? 'default' : 'outline'}><Link href={status ? `/knowledge?status=${status}` : '/knowledge'}>{status || 'all'}</Link></Button>)}</div></div>
        <div className="grid gap-4 xl:grid-cols-2">
          {visiblePrinciples.map((principle) => (
            <article className="rounded-lg border border-gray-800 bg-black/30 p-4" key={principle.id}>
              <div className="flex flex-wrap items-center gap-2"><Badge variant="outline" className={statusTone(principle.status)}>{principle.status}</Badge><Badge variant="outline">{principle.category}</Badge><span className="text-xs text-gray-500">v{principle.version} · confidence {(Number(principle.confidence) * 100).toFixed(0)}%</span></div>
              <h3 className="mt-3 font-semibold leading-6 text-gray-100">{principle.principle}</h3>
              <blockquote className="mt-3 border-l-2 border-teal-900 pl-3 text-sm italic leading-6 text-gray-400">{principle.exact_fragment}</blockquote>
              <div className="mt-3 text-xs text-gray-500">{documentNames.get(principle.knowledge_document_id) ?? `Document #${principle.knowledge_document_id}`} · page {principle.page_number ?? 'n/a'}</div>
              {principle.application_conditions.length ? <p className="mt-3 text-sm text-gray-300"><span className="font-semibold text-gray-400">Apply when:</span> {principle.application_conditions.join('; ')}</p> : null}
              {principle.exceptions.length ? <p className="mt-2 text-sm text-amber-200"><span className="font-semibold">Exceptions:</span> {principle.exceptions.join('; ')}</p> : null}
              {principle.semantic_duplicate_of_id ? <div className="mt-3 rounded border border-amber-900/60 bg-amber-950/20 p-2 text-xs text-amber-200">Possible duplicate of principle #{principle.semantic_duplicate_of_id}. Review before approval.</div> : null}
              {principle.status === 'proposed' ? <div className="mt-4 flex flex-wrap gap-2"><MutationForm action={decideKnowledgePrinciple.bind(null, principle.id, 'approve')} successMessage="Principle approved"><Button size="sm" type="submit"><Check className="h-4 w-4" />Approve</Button></MutationForm><MutationForm action={decideKnowledgePrinciple.bind(null, principle.id, 'reject')} successMessage="Principle rejected"><Button size="sm" type="submit" variant="outline"><X className="h-4 w-4" />Reject</Button></MutationForm>{principle.semantic_duplicate_of_id ? <MutationForm action={mergeKnowledgePrinciple.bind(null, principle.id, principle.semantic_duplicate_of_id)} successMessage="Principle merged"><Button size="sm" type="submit" variant="outline">Merge duplicate</Button></MutationForm> : null}</div> : null}
              {['proposed', 'approved'].includes(principle.status) ? <details className="mt-4 border-t border-gray-800 pt-3"><summary className="cursor-pointer text-xs font-semibold uppercase text-gray-500">Correct as new version</summary><MutationForm action={reviseKnowledgePrinciple.bind(null, principle.id)} className="mt-3 grid gap-2" successMessage="Revision proposed"><Textarea defaultValue={principle.principle} name="principle" required /><Input defaultValue={principle.category} name="category" required /><Input defaultValue={principle.application_conditions.join(', ')} name="application_conditions" placeholder="Conditions, comma-separated" /><Input defaultValue={principle.exceptions.join(', ')} name="exceptions" placeholder="Exceptions, comma-separated" /><Button className="w-fit" size="sm" type="submit">Create revision</Button></MutationForm></details> : null}
            </article>
          ))}
          {!visiblePrinciples.length ? <p className="text-sm text-gray-500">No principles match this filter.</p> : null}
        </div>
      </section>
    </main>
  );
}

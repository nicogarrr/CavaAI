import Link from 'next/link';
import { BookOpen, Check, FileSearch, Library, Sparkles, UploadCloud, X } from 'lucide-react';

import { MutationForm } from '@/components/forms/MutationForm';
import { FileUploadInput } from '@/components/forms/FileUploadInput';
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
import BackendOffline from '@/components/system/BackendOffline';
import { isBackendUnavailableError } from '@/lib/backend-offline';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type PageProps = { searchParams: Promise<{ document?: string; status?: string }> };

const PRINCIPLE_STATUS_LABELS: Record<string, string> = {
  '': 'todos',
  proposed: 'propuestos',
  approved: 'aprobados',
  rejected: 'rechazados',
  merged: 'fusionados',
  superseded: 'sustituidos',
};

/** Etiquetas en español para los estados persistidos por el backend */
const STATUS_LABELS: Record<string, string> = {
  queued: 'en cola',
  running: 'en curso',
  succeeded: 'completada',
  failed: 'fallida',
  pending: 'pendiente',
  processing: 'procesando',
  ready: 'lista',
  proposed: 'propuesto',
  approved: 'aprobado',
  rejected: 'rechazado',
  merged: 'fusionado',
  superseded: 'sustituido',
};

function label(value: string | null | undefined): string {
  if (!value) return '—';
  return STATUS_LABELS[value] ?? value.replaceAll('_', ' ');
}

function statusTone(status: string) {
  if (status === 'approved' || status === 'ready') return 'border-teal-800 text-teal-300';
  if (status === 'rejected') return 'border-red-900 text-red-300';
  return 'border-amber-900 text-amber-300';
}

export default async function KnowledgeLibraryPage({ searchParams }: PageProps) {
  const query = await searchParams;
  const selectedDocumentId = Number(query.document) || null;
  const fetchAll = () =>
    Promise.all([getKnowledgeLibrary(), getKnowledgeDocumentChunks(selectedDocumentId)]);
  let data: Awaited<ReturnType<typeof fetchAll>>;
  try {
    data = await fetchAll();
  } catch (error) {
    if (isBackendUnavailableError(error)) {
      return <BackendOffline feature="Knowledge Library" retryHref="/knowledge" />;
    }
    throw error;
  }
  const [{ collections, documents, principles, jobs }, chunks] = data;
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
    <main id="content" tabIndex={-1} className="mx-auto flex w-full min-w-0 max-w-7xl flex-col gap-6 overflow-x-clip">
      <header className="flex flex-col gap-4 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase text-teal-300">Conocimiento de inversión</p>
          <h1 className="mt-1 text-3xl font-bold text-gray-100">Biblioteca de conocimiento</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Libros, cartas y casos de estudio separados de la evidencia de empresas, con principios aprobados por humanos y trazables.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:flex sm:flex-wrap">
          <Button asChild className="h-11 w-full sm:w-auto" variant="outline"><Link href="/search"><FileSearch className="h-4 w-4" />Buscar en todo</Link></Button>
          <Button asChild className="h-11 w-full sm:w-auto" variant="outline"><Link href="/knowledge-graph"><Library className="h-4 w-4" />Grafo de conocimiento</Link></Button>
          <MutationForm action={installKnowledgeDefaults} className="w-full sm:w-auto" successMessage="Colecciones por defecto listas">
            <Button className="h-11 w-full sm:w-auto" type="submit"><Library className="h-4 w-4" />Instalar por defecto</Button>
          </MutationForm>
        </div>
      </header>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
        {[
          ['Colecciones', collections.length],
          ['Documentos', documents.length],
          ['Pendientes de aprobación', principles.filter((item) => item.status === 'proposed').length],
        ].map(([label, value]) => (
          <div className="rounded-xl border border-gray-800 bg-[#101010] p-4" key={label}>
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</div>
            <div className="mt-2 text-2xl font-semibold text-gray-100">{value}</div>
          </div>
        ))}
      </section>

      {activeJobs.length ? (
        <section className="rounded-xl border border-amber-900/60 bg-amber-950/10 p-4 text-sm text-amber-100">
          <div className="font-semibold">Extracción en segundo plano en curso</div>
          <div className="mt-2 grid gap-1 text-amber-200/80">
            {activeJobs.map((job) => (
              <div key={job.id}>Tarea #{job.id} · {documentNames.get(job.entity_id ?? -1) ?? `documento ${job.entity_id}`} · {label(job.status)}{job.progress_total ? ` · lote ${job.progress_current}/${job.progress_total}` : ''}</div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="grid grid-cols-1 gap-4 sm:gap-6 xl:grid-cols-2">
        <MutationForm action={createKnowledgeCollection} className="rounded-xl border border-gray-800 bg-[#101010] p-5" resetOnSuccess successMessage="Colección creada">
          <div className="mb-4 flex items-center gap-2"><Library className="h-5 w-5 text-teal-300" /><h2 className="font-semibold text-gray-100">Nueva colección</h2></div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input className="h-11 w-full" name="name" placeholder="Compounders de calidad" required />
            <Input className="h-11 w-full" name="collection_type" defaultValue="custom" placeholder="Tipo de colección" required />
            <Textarea className="min-h-[88px] w-full sm:col-span-2" name="description" placeholder="Ámbito y uso previsto" />
            <Button className="h-11 w-full sm:col-span-2 sm:w-fit" type="submit">Crear colección</Button>
          </div>
        </MutationForm>

        <MutationForm id="upload-knowledge" action={uploadKnowledgeDocument} className="rounded-xl border border-gray-800 bg-[#101010] p-5" resetOnSuccess successMessage="Documento ingerido">
          <div className="mb-4 flex items-center gap-2"><UploadCloud className="h-5 w-5 text-teal-300" /><h2 className="font-semibold text-gray-100">Subir conocimiento</h2></div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input className="h-11 w-full" name="title" placeholder="Título del documento" required />
            <select className="h-11 w-full rounded-md border border-gray-800 bg-black px-3 text-base text-gray-200 md:text-sm" name="collection_id" defaultValue="">
              <option value="">Sin colección</option>
              {collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}
            </select>
            <Input className="h-11 w-full" name="author" placeholder="Autor" />
            <Input className="h-11 w-full" name="document_type" defaultValue="book" placeholder="libro, carta, paper" required />
            <Input className="h-11 w-full" name="publication_date" type="date" />
            <Input className="h-11 w-full" name="language" defaultValue="en" placeholder="Idioma" />
            <Input className="h-11 w-full sm:col-span-2" name="source_url" placeholder="URL de la fuente (opcional)" type="url" />
            <FileUploadInput accept=".pdf,.docx,.txt,.md,.html,.xlsx,.csv" className="h-11 w-full sm:col-span-2" name="file" required />
            <Button className="h-11 w-full sm:col-span-2 sm:w-fit" type="submit"><UploadCloud className="h-4 w-4" />Subir</Button>
          </div>
        </MutationForm>
      </section>

      <section className="min-w-0 rounded-xl border border-gray-800 bg-[#101010] p-4 sm:p-5">
        <div className="mb-4 flex items-center gap-2"><BookOpen className="h-5 w-5 text-teal-300" /><h2 className="text-lg font-semibold text-gray-100">Documentos</h2></div>
        {!documents.length ? <div className="py-2 text-sm text-gray-500"><p>Aún no hay documentos de conocimiento.</p><a className="mt-2 inline-flex items-center gap-2 rounded-md border border-teal-800 px-3 py-2 text-xs font-medium text-teal-300 hover:border-teal-600 hover:text-teal-200" href="#upload-knowledge">Sube tu primer libro, carta o caso de estudio</a></div> : null}
        <div className="hidden overflow-x-auto md:block">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="text-xs uppercase text-gray-500"><tr><th className="border-b border-gray-800 py-2">Documento</th><th className="border-b border-gray-800 py-2">Colección</th><th className="border-b border-gray-800 py-2">Tipo</th><th className="border-b border-gray-800 py-2">Extractor</th><th className="border-b border-gray-800 py-2">Estado</th><th className="border-b border-gray-800 py-2 text-right">Acciones</th></tr></thead>
            <tbody>
              {documents.map((document) => {
                const job = latestJobByDocument.get(document.id);
                const busy = job?.status === 'queued' || job?.status === 'running';
                return (
                <tr className="border-b border-gray-900" key={document.id}>
                  <td className="py-3"><div className="font-medium text-gray-200">{document.title}</div><div className="text-xs text-gray-500">{document.author ?? 'Autor desconocido'} · {document.publication_date ?? 'sin fecha'}</div></td>
                  <td className="py-3 text-gray-400">{document.collection_id ? collectionNames.get(document.collection_id) : 'Sin colección'}</td>
                  <td className="py-3 text-gray-400">{document.document_type}</td>
                  <td className="py-3 text-gray-500">{String(document.metadata.parser ?? 'desconocido')}</td>
                  <td className="py-3"><Badge className={statusTone(document.status)} variant="outline">{label(document.status)}</Badge></td>
                  <td className="py-3"><div className="flex justify-end gap-2"><Button asChild size="sm" variant="outline"><Link href={`/knowledge?document=${document.id}`}>Fragmentos</Link></Button><MutationForm action={extractKnowledgePrinciples.bind(null, document.id)} successMessage="Extracción encolada"><Button disabled={busy} size="sm" type="submit"><Sparkles className="h-4 w-4" />{busy ? label(job?.status) : 'Extraer'}</Button></MutationForm></div>{job?.status === 'failed' ? <div className="mt-1 max-w-xs text-right text-xs text-red-300">{job.error}</div> : null}</td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="grid grid-cols-1 gap-3 md:hidden">
          {documents.map((document) => {
            const job = latestJobByDocument.get(document.id);
            const busy = job?.status === 'queued' || job?.status === 'running';
            return (
              <article className="min-w-0 rounded-lg border border-gray-800 bg-black/30 p-4 break-words" key={document.id}>
                <div className="min-w-0 font-medium text-gray-200">{document.title}</div>
                <div className="mt-1 text-xs text-gray-500">{document.author ?? 'Autor desconocido'} · {document.publication_date ?? 'sin fecha'}</div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{document.collection_id ? collectionNames.get(document.collection_id) : 'Sin colección'}</Badge>
                  <Badge variant="outline">{document.document_type}</Badge>
                  <Badge className={statusTone(document.status)} variant="outline">{label(document.status)}</Badge>
                </div>
                <div className="mt-2 text-xs text-gray-500">Extractor: {String(document.metadata.parser ?? 'desconocido')}</div>
                {job?.status === 'failed' ? <div className="mt-2 text-xs text-red-300">{job.error}</div> : null}
                <div className="mt-4 grid grid-cols-1 gap-2">
                  <Button asChild className="h-11 w-full" size="sm" variant="outline"><Link href={`/knowledge?document=${document.id}`}>Fragmentos</Link></Button>
                  <MutationForm action={extractKnowledgePrinciples.bind(null, document.id)} successMessage="Extracción encolada">
                    <Button className="h-11 w-full" disabled={busy} size="sm" type="submit"><Sparkles className="h-4 w-4" />{busy ? label(job?.status) : 'Extraer'}</Button>
                  </MutationForm>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {selectedDocument ? (
        <section className="min-w-0 rounded-xl border border-teal-900/50 bg-[#101010] p-4 sm:p-5">
          <div className="mb-4 flex items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase text-teal-300">Explorador de fragmentos</p><h2 className="text-lg font-semibold text-gray-100">{selectedDocument.title}</h2></div><Button asChild size="sm" variant="ghost"><Link href="/knowledge">Cerrar</Link></Button></div>
          <div className="grid max-h-[620px] gap-3 overflow-y-auto pr-2">
            {chunks.map((chunk) => <article className="rounded-lg border border-gray-800 bg-black/30 p-4" key={chunk.id}><div className="mb-2 flex justify-between text-xs text-gray-500"><span>Fragmento {chunk.chunk_index + 1}</span><span>página {chunk.page_number ?? 's/d'} · {chunk.token_count} tokens</span></div><p className="whitespace-pre-wrap text-sm leading-6 text-gray-300">{chunk.content}</p></article>)}
            {!chunks.length ? <p className="text-sm text-gray-500">Este documento no tiene fragmentos.</p> : null}
          </div>
        </section>
      ) : null}

      <section className="min-w-0 rounded-xl border border-gray-800 bg-[#101010] p-4 sm:p-5">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center"><div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-teal-300" /><h2 className="text-lg font-semibold text-gray-100">Principios de inversión</h2></div><div className="flex flex-wrap gap-2 md:ml-auto">{['', 'proposed', 'approved', 'rejected', 'merged', 'superseded'].map((status) => <Button asChild className="min-h-[44px]" key={status || 'all'} size="sm" variant={(query.status ?? '') === status ? 'default' : 'outline'}><Link href={status ? `/knowledge?status=${status}` : '/knowledge'}>{PRINCIPLE_STATUS_LABELS[status] ?? status}</Link></Button>)}</div></div>
        <div className="grid gap-4 xl:grid-cols-2">
          {visiblePrinciples.map((principle) => (
            <article className="min-w-0 rounded-lg border border-gray-800 bg-black/30 p-4 break-words" key={principle.id}>
              <div className="flex flex-wrap items-center gap-2"><Badge variant="outline" className={statusTone(principle.status)}>{label(principle.status)}</Badge><Badge variant="outline">{principle.category}</Badge><span className="text-xs text-gray-500">v{principle.version} · confianza {(Number(principle.confidence) * 100).toFixed(0)}%</span></div>
              <h3 className="mt-3 font-semibold leading-6 text-gray-100">{principle.principle}</h3>
              <blockquote className="mt-3 border-l-2 border-teal-900 pl-3 text-sm italic leading-6 text-gray-400">{principle.exact_fragment}</blockquote>
              <div className="mt-3 text-xs text-gray-500">{documentNames.get(principle.knowledge_document_id) ?? `Documento #${principle.knowledge_document_id}`} · página {principle.page_number ?? 's/d'}</div>
              {principle.application_conditions.length ? <p className="mt-3 text-sm text-gray-300"><span className="font-semibold text-gray-400">Aplicar cuando:</span> {principle.application_conditions.join('; ')}</p> : null}
              {principle.exceptions.length ? <p className="mt-2 text-sm text-amber-200"><span className="font-semibold">Excepciones:</span> {principle.exceptions.join('; ')}</p> : null}
              {principle.semantic_duplicate_of_id ? <div className="mt-3 rounded border border-amber-900/60 bg-amber-950/20 p-2 text-xs text-amber-200">Posible duplicado del principio #{principle.semantic_duplicate_of_id}. Revísalo antes de aprobar.</div> : null}
              {principle.status === 'proposed' ? <div className="mt-4 flex flex-wrap gap-2"><MutationForm action={decideKnowledgePrinciple.bind(null, principle.id, 'approve')} successMessage="Principio aprobado"><Button className="min-h-[44px]" size="sm" type="submit"><Check className="h-4 w-4" />Aprobar</Button></MutationForm><MutationForm action={decideKnowledgePrinciple.bind(null, principle.id, 'reject')} successMessage="Principio rechazado"><Button className="min-h-[44px]" size="sm" type="submit" variant="outline"><X className="h-4 w-4" />Rechazar</Button></MutationForm>{principle.semantic_duplicate_of_id ? <MutationForm action={mergeKnowledgePrinciple.bind(null, principle.id, principle.semantic_duplicate_of_id)} successMessage="Principio fusionado"><Button className="min-h-[44px]" size="sm" type="submit" variant="outline">Fusionar duplicado</Button></MutationForm> : null}</div> : null}
              {['proposed', 'approved'].includes(principle.status) ? <details className="mt-4 border-t border-gray-800 pt-3"><summary className="cursor-pointer text-xs font-semibold uppercase text-gray-500">Corregir como nueva versión</summary><MutationForm action={reviseKnowledgePrinciple.bind(null, principle.id)} className="mt-3 grid grid-cols-1 gap-2" successMessage="Revisión propuesta"><Textarea className="min-h-[88px] w-full text-base md:text-sm" defaultValue={principle.principle} name="principle" required /><Input className="h-11 w-full" defaultValue={principle.category} name="category" required /><Input className="h-11 w-full" defaultValue={principle.application_conditions.join(', ')} name="application_conditions" placeholder="Condiciones, separadas por comas" /><Input className="h-11 w-full" defaultValue={principle.exceptions.join(', ')} name="exceptions" placeholder="Excepciones, separadas por comas" /><Button className="h-11 w-full sm:w-fit" size="sm" type="submit">Crear revisión</Button></MutationForm></details> : null}
            </article>
          ))}
          {!visiblePrinciples.length ? <p className="text-sm text-gray-500">Ningún principio coincide con este filtro.</p> : null}
        </div>
      </section>
    </main>
  );
}

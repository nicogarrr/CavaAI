import Link from 'next/link';
import { ArrowLeft, FileText, ShieldCheck, UploadCloud } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { MutationForm } from '@/components/forms/MutationForm';
import {
  getResearchSources,
  importResearchDocumentFile,
  importResearchDocumentUrl,
  importResearchSource,
} from '@/lib/actions/research.actions';
import { formatDate, formatNumber, NA } from '@/lib/format';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function ResearchSourcesPage() {
  const { documents, audits } = await getResearchSources();

  return (
    <main id="content" tabIndex={-1} className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="flex flex-col gap-4 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <Button asChild className="mb-4" size="sm" variant="ghost">
            <Link href="/research">
              <ArrowLeft aria-hidden="true" className="h-4 w-4" />
              Research
            </Link>
          </Button>
          <p className="text-sm font-semibold uppercase text-teal-300">Evidencia</p>
          <h1 className="mt-1 text-3xl font-bold text-gray-100">Fuentes</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Documentos, transcripts y auditorías que alimentan tesis, RAG y valoraciones.
          </p>
        </div>
        <div className="rounded-lg border border-gray-800 bg-[#111111] px-4 py-3 text-sm text-gray-300">
          {formatNumber(documents.length, { maximumFractionDigits: 0 })} documentos ·{' '}
          {formatNumber(audits.length, { maximumFractionDigits: 0 })} auditorías
        </div>
      </header>

      <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <MutationForm action={importResearchSource} className="rounded-lg border border-gray-800 bg-[#111111] p-5" resetOnSuccess successMessage="Fuente importada">
          <div className="mb-4 flex items-center gap-2">
            <UploadCloud aria-hidden="true" className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Importar fuente manual</h2>
          </div>
          <div className="grid gap-3">
            <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
              <label className="text-sm font-semibold text-gray-400" htmlFor="ticker">Ticker</label>
              <Input id="ticker" name="ticker" placeholder="MSFT" required />
            </div>
            <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
              <label className="text-sm font-semibold text-gray-400" htmlFor="period">Periodo</label>
              <Input id="period" name="period" placeholder="Q2 2026" />
            </div>
            <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
              <label className="text-sm font-semibold text-gray-400" htmlFor="title">Título</label>
              <Input id="title" name="title" placeholder="Transcript de la llamada de resultados del Q2" required />
            </div>
            <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
              <label className="text-sm font-semibold text-gray-400" htmlFor="source_url">URL</label>
              <Input id="source_url" name="source_url" placeholder="https://..." />
            </div>
            <div className="grid gap-2">
              <label className="text-sm font-semibold text-gray-400" htmlFor="text">Texto</label>
              <Textarea
                className="min-h-[260px] border-gray-800 bg-black/30 text-gray-200 focus-visible:ring-teal-500"
                id="text"
                name="text"
                placeholder="Pega el transcript, la nota de RI, el artículo o el extracto del filing"
                required
              />
            </div>
            <Button className="w-full sm:w-fit" type="submit">
              <UploadCloud aria-hidden="true" className="h-4 w-4" />
              Importar fuente
            </Button>
          </div>
        </MutationForm>

        <section className="grid gap-6">
          <MutationForm action={importResearchDocumentFile} className="rounded-lg border border-gray-800 bg-[#111111] p-5" resetOnSuccess successMessage="Documento importado">
            <div className="mb-4 flex items-center gap-2">
              <UploadCloud aria-hidden="true" className="h-5 w-5 text-teal-300" />
              <h2 className="text-lg font-semibold text-gray-100">Subir documento</h2>
            </div>
            <div className="grid gap-3">
              <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
                <label className="text-sm font-semibold text-gray-400" htmlFor="file-ticker">Ticker</label>
                <Input id="file-ticker" name="ticker" placeholder="MSFT" required />
              </div>
              <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
                <label className="text-sm font-semibold text-gray-400" htmlFor="file-title">Título</label>
                <Input id="file-title" name="title" placeholder="Informe anual, presentación, transcript..." required />
              </div>
              <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
                <label className="text-sm font-semibold text-gray-400" htmlFor="file-source-type">Tipo de fuente</label>
                <Input id="file-source-type" name="source_type" placeholder="filing, company_ir, transcript" defaultValue="manual_upload" />
              </div>
              <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
                <label className="text-sm font-semibold text-gray-400" htmlFor="file-source-url">URL de la fuente</label>
                <Input id="file-source-url" name="source_url" placeholder="https://..." />
              </div>
              <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
                <label className="text-sm font-semibold text-gray-400" htmlFor="file">Archivo</label>
                <Input accept=".txt,.md,.html,.htm,.pdf,.docx,.xlsx,.csv,.tsv" id="file" name="file" required type="file" />
              </div>
              <Button className="w-full sm:w-fit" type="submit">
              <UploadCloud aria-hidden="true" className="h-4 w-4" />
              Subir documento
              </Button>
            </div>
          </MutationForm>

          <MutationForm action={importResearchDocumentUrl} className="rounded-lg border border-gray-800 bg-[#111111] p-5" resetOnSuccess successMessage="URL importada">
            <div className="mb-4 flex items-center gap-2">
              <FileText aria-hidden="true" className="h-5 w-5 text-teal-300" />
              <h2 className="text-lg font-semibold text-gray-100">Ingerir desde URL</h2>
            </div>
            <div className="grid gap-3">
              <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
                <label className="text-sm font-semibold text-gray-400" htmlFor="url-ticker">Ticker</label>
                <Input id="url-ticker" name="ticker" placeholder="MSFT" required />
              </div>
              <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
                <label className="text-sm font-semibold text-gray-400" htmlFor="url-title">Título</label>
                <Input id="url-title" name="title" placeholder="Nota de prensa de RI o página del filing" required />
              </div>
              <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
                <label className="text-sm font-semibold text-gray-400" htmlFor="url-source-type">Tipo de fuente</label>
                <Input id="url-source-type" name="source_type" placeholder="url, company_ir, filing" defaultValue="url" />
              </div>
              <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
                <label className="text-sm font-semibold text-gray-400" htmlFor="url">URL</label>
                <Input id="url" name="url" placeholder="https://..." required type="url" />
              </div>
              <Button className="w-full sm:w-fit" type="submit" variant="outline">
              <UploadCloud aria-hidden="true" className="h-4 w-4" />
              Ingerir URL
              </Button>
            </div>
          </MutationForm>
        </section>

        <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <ShieldCheck aria-hidden="true" className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Auditorías de fuentes</h2>
          </div>
          <div className="grid gap-3">
            {audits.slice(0, 8).map((audit) => (
              <div key={audit.id} className="rounded-md border border-gray-800 bg-black/30 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className={audit.passed ? 'font-semibold text-teal-300' : 'font-semibold text-amber-300'}>
                    {audit.passed ? 'superada' : 'bloqueada'}
                  </span>
                  <span className="text-sm text-gray-500">cobertura {formatNumber(audit.source_coverage_score, { maximumFractionDigits: 2 })}</span>
                </div>
                <div className="mt-2 text-sm text-gray-400">
                  Tesis #{audit.thesis_version_id ?? NA}
                </div>
                {audit.required_fixes.length ? (
                  <div className="mt-2 text-xs text-amber-200">{audit.required_fixes.join('; ')}</div>
                ) : null}
              </div>
            ))}
            {!audits.length ? (
              <div className="rounded-md border border-dashed border-gray-800 p-4 text-center text-sm text-gray-500">
                <p>Sin auditorías todavía.</p>
                <Link className="mt-3 inline-flex items-center gap-2 rounded-md border border-teal-800 px-3 py-2 text-xs font-medium text-teal-300 hover:border-teal-600 hover:text-teal-200" href="/research/MSFT?view=thesis">
                  Genera una tesis para disparar la primera auditoría
                </Link>
              </div>
            ) : null}
          </div>
        </section>
      </section>

      <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
        <div className="mb-4 flex items-center gap-2">
          <FileText aria-hidden="true" className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Documentos</h2>
        </div>
        <div aria-label="Documentos importados" className="overflow-x-auto" role="region" tabIndex={0}>
          <table className="w-full min-w-[820px] text-left text-sm">
            <caption className="sr-only">Documentos, transcripts y auditorías que alimentan la evidencia, con fuente, nivel y fecha de publicación</caption>
            <thead className="text-xs uppercase text-gray-500">
              <tr>
                <th className="border-b border-gray-800 py-2" scope="col">Ticker</th>
                <th className="border-b border-gray-800 py-2" scope="col">Título</th>
                <th className="border-b border-gray-800 py-2" scope="col">Fuente</th>
                <th className="border-b border-gray-800 py-2" scope="col">Nivel</th>
                <th className="border-b border-gray-800 py-2" scope="col">Publicado</th>
                <th className="border-b border-gray-800 py-2" scope="col">URL</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => (
                <tr key={document.id} className="border-b border-gray-900 last:border-0">
                  <th className="py-3 text-left text-sm font-semibold text-gray-200" scope="row">{document.ticker ?? 'GLOBAL'}</th>
                  <td className="py-3 text-gray-300">{document.title}</td>
                  <td className="py-3 text-gray-400">{document.source_type}</td>
                  <td className="py-3 text-gray-400">{document.source_tier}</td>
                  <td className="py-3 text-gray-500">{formatDate(document.published_at, undefined, NA)}</td>
                  <td className="py-3 text-gray-500">
                    {document.source_url ? (
                      <a className="text-teal-300 hover:text-teal-200" href={document.source_url} rel="noreferrer" target="_blank">
                        abrir
                      </a>
                    ) : (
                      NA
                    )}
                  </td>
                </tr>
              ))}
              {!documents.length ? (
                <tr>
                  <td className="py-6 text-center text-gray-500" colSpan={6}>
                    <p>Sin documentos importados.</p>
                    <span className="mt-2 block text-xs text-gray-500">
                      Usa los formularios de arriba para subir tu primer documento o ingerir una URL.
                    </span>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

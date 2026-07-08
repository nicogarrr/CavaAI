import Link from 'next/link';
import { ArrowLeft, FileText, ShieldCheck, UploadCloud } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { getResearchSources, importResearchSource } from '@/lib/actions/research.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function ResearchSourcesPage() {
  const { documents, audits } = await getResearchSources();

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
          <p className="text-sm font-semibold uppercase text-teal-300">Evidence</p>
          <h1 className="mt-1 text-3xl font-bold text-gray-100">Sources</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Documentos, transcripts y auditorias que alimentan tesis, RAG y valoraciones.
          </p>
        </div>
        <div className="rounded-lg border border-gray-800 bg-[#111111] px-4 py-3 text-sm text-gray-300">
          {documents.length} documentos - {audits.length} auditorias
        </div>
      </header>

      <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <form action={importResearchSource} className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <UploadCloud className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Import Manual Source</h2>
          </div>
          <div className="grid gap-3">
            <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
              <label className="text-sm font-semibold text-gray-400" htmlFor="ticker">Ticker</label>
              <Input id="ticker" name="ticker" placeholder="MSFT" required />
            </div>
            <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
              <label className="text-sm font-semibold text-gray-400" htmlFor="period">Period</label>
              <Input id="period" name="period" placeholder="Q2 2026" />
            </div>
            <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
              <label className="text-sm font-semibold text-gray-400" htmlFor="title">Title</label>
              <Input id="title" name="title" placeholder="Q2 earnings call transcript" required />
            </div>
            <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
              <label className="text-sm font-semibold text-gray-400" htmlFor="source_url">URL</label>
              <Input id="source_url" name="source_url" placeholder="https://..." />
            </div>
            <div className="grid gap-2">
              <label className="text-sm font-semibold text-gray-400" htmlFor="text">Text</label>
              <Textarea
                className="min-h-[260px] border-gray-800 bg-black/30 text-gray-200 focus-visible:ring-teal-500"
                id="text"
                name="text"
                placeholder="Paste transcript, IR note, article or filing excerpt"
                required
              />
            </div>
            <Button className="w-full sm:w-fit" type="submit">
              <UploadCloud className="h-4 w-4" />
              Import Source
            </Button>
          </div>
        </form>

        <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-teal-300" />
            <h2 className="text-lg font-semibold text-gray-100">Source Audits</h2>
          </div>
          <div className="grid gap-3">
            {audits.slice(0, 8).map((audit) => (
              <div key={audit.id} className="rounded-md border border-gray-800 bg-black/30 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className={audit.passed ? 'font-semibold text-teal-300' : 'font-semibold text-amber-300'}>
                    {audit.passed ? 'passed' : 'blocked'}
                  </span>
                  <span className="text-sm text-gray-500">score {audit.source_coverage_score}</span>
                </div>
                <div className="mt-2 text-sm text-gray-400">
                  Thesis #{audit.thesis_version_id ?? 'n/a'}
                </div>
                {audit.required_fixes.length ? (
                  <div className="mt-2 text-xs text-amber-200">{audit.required_fixes.join('; ')}</div>
                ) : null}
              </div>
            ))}
            {!audits.length ? (
              <div className="rounded-md border border-gray-800 p-3 text-sm text-gray-500">Sin auditorias todavia.</div>
            ) : null}
          </div>
        </section>
      </section>

      <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
        <div className="mb-4 flex items-center gap-2">
          <FileText className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Documents</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="text-xs uppercase text-gray-500">
              <tr>
                <th className="border-b border-gray-800 py-2">Ticker</th>
                <th className="border-b border-gray-800 py-2">Title</th>
                <th className="border-b border-gray-800 py-2">Source</th>
                <th className="border-b border-gray-800 py-2">Published</th>
                <th className="border-b border-gray-800 py-2">URL</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => (
                <tr key={document.id} className="border-b border-gray-900 last:border-0">
                  <td className="py-3 font-semibold text-gray-200">{document.ticker ?? 'GLOBAL'}</td>
                  <td className="py-3 text-gray-300">{document.title}</td>
                  <td className="py-3 text-gray-400">{document.source_type}</td>
                  <td className="py-3 text-gray-500">{document.published_at ?? 'n/a'}</td>
                  <td className="py-3 text-gray-500">
                    {document.source_url ? (
                      <a className="text-teal-300 hover:text-teal-200" href={document.source_url} rel="noreferrer" target="_blank">
                        open
                      </a>
                    ) : (
                      'n/a'
                    )}
                  </td>
                </tr>
              ))}
              {!documents.length ? (
                <tr>
                  <td className="py-4 text-gray-500" colSpan={5}>Sin documentos importados.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

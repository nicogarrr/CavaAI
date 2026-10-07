import { ArrowLeft, Layers, Play } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { getResearchWorkflows, runResearchWorkflow } from '@/lib/actions/research.actions';
import { MutationForm } from '@/components/forms/MutationForm';
import { formatNumber } from '@/lib/format';
import { workflowSummary } from '@/lib/research/workflow-summary';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

async function runWorkflow(formData: FormData) {
  'use server';
  const name = String(formData.get('workflow'));
  const ticker = String(formData.get('ticker') || '');
  await runResearchWorkflow(name, ticker || undefined);
}

export default async function ResearchWorkflowsPage() {
  const workflows = await getResearchWorkflows();
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
          <p className="text-sm font-semibold uppercase text-teal-300">Automatización</p>
          <h1 className="mt-1 text-3xl font-bold text-gray-100">Flujos de trabajo</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Genera una tesis o consulta las tareas de investigación disponibles.
          </p>
        </div>
        <div className="rounded-lg border border-gray-800 bg-surface-1 px-4 py-3 text-sm text-gray-300">
          {formatNumber(workflows.length, { maximumFractionDigits: 0 })} flujos
        </div>
      </header>

      <section className="grid gap-4 xl:grid-cols-2">
        {workflows.map((workflow) => {
          const needsTicker = workflow.input.toLowerCase().includes('ticker');
          const isGenerateThesis = workflow.name === 'GenerateThesisWorkflow';
          const status = workflow.implementation_status ?? 'descriptive';
          const statusStyles: Record<string, string> = {
            implemented: 'border-teal-800 bg-teal-950/30 text-teal-300',
            partial: 'border-amber-800 bg-amber-950/30 text-amber-300',
            descriptive: 'border-gray-700 bg-gray-900 text-gray-500',
          };
          const statusLabels: Record<string, string> = {
            implemented: 'ejecutable',
            partial: 'Parcial',
            descriptive: 'descriptivo',
          };

          return (
            <div key={workflow.name} className="min-w-0 rounded-lg border border-gray-800 bg-surface-1 p-5">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Layers aria-hidden="true" className="h-5 w-5 text-teal-300" />
                <span className="min-w-0 break-all font-semibold text-gray-100">{workflow.name}</span>
                <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${statusStyles[status]}`}>
                  {statusLabels[status]}
                </span>
                <span className="rounded-full border border-gray-700 bg-gray-900 px-2 py-0.5 text-xs text-gray-400">
                  entrada: {workflow.input}
                </span>
              </div>
              <p className="mb-4 text-sm leading-6 text-gray-400">{workflowSummary(workflow.name)}</p>
              <details className="mb-4 text-xs text-gray-500">
                <summary className="min-h-11 cursor-pointer py-3">Detalles técnicos</summary>
                {workflow.truth ? (
                  <p className="mb-3 leading-5">{workflow.truth}</p>
                ) : null}
                <ol className="space-y-1">
                  {workflow.steps.map((step, index) => (
                    <li key={`${workflow.name}-${index}`} className="flex items-start gap-2">
                      <span className="mt-0.5 font-mono text-teal-300/60">{String(index + 1).padStart(2, '0')}</span>
                      <span className="min-w-0 break-all font-mono text-gray-400">{step}</span>
                    </li>
                  ))}
                </ol>
              </details>

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-800 pt-3">
                <div className="flex items-center gap-1.5 text-xs text-gray-500">
                  {status === 'implemented'
                    ? isGenerateThesis ? 'Generación de una nueva versión' : 'Disponible mediante API'
                    : status === 'partial'
                      ? 'Ejecución parcial mediante API'
                      : 'No se ejecuta desde esta pantalla'}
                </div>
                {isGenerateThesis ? (
                  <MutationForm action={runWorkflow} className="flex flex-wrap items-center gap-2" successMessage="Flujo ejecutado">
                    <input name="workflow" type="hidden" value={workflow.name} />
                    {needsTicker && (
                      <Input
                        className="h-8 w-28 border-gray-700 bg-black/30 text-gray-200 text-sm"
                        aria-label="Ticker de la empresa"
                        name="ticker"
                        placeholder="MSFT"
                        required
                      />
                    )}
                    <Button size="sm" type="submit" variant="outline">
                      <Play aria-hidden="true" className="h-3.5 w-3.5" />
                      Ejecutar
                    </Button>
                  </MutationForm>
                ) : status !== 'descriptive' ? (
                  <span className="min-w-0 break-all text-right text-xs text-gray-500">
                    Sin ejecución desde esta pantalla
                  </span>
                ) : null}
              </div>
            </div>
          );
        })}
        {!workflows.length ? (
          <div className="col-span-2 rounded-lg border border-gray-800 bg-surface-1 p-5 text-sm text-gray-500">
            No hay flujos registrados.
          </div>
        ) : null}
      </section>
    </main>
  );
}

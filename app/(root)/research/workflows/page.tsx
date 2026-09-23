import { ArrowLeft, Layers, Play } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { getResearchDashboard, runResearchWorkflow } from '@/lib/actions/research.actions';
import { MutationForm } from '@/components/forms/MutationForm';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

async function runWorkflow(formData: FormData) {
  'use server';
  const name = String(formData.get('workflow'));
  const ticker = String(formData.get('ticker') || '');
  await runResearchWorkflow(name, ticker || undefined);
}

export default async function ResearchWorkflowsPage() {
  const { workflows } = await getResearchDashboard();
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
          <p className="text-sm font-semibold uppercase text-teal-300">Automatización</p>
          <h1 className="mt-1 text-3xl font-bold text-gray-100">Flujos de trabajo</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Flujos de investigación orquestados por el backend Python. Ejecuta GenerateThesisWorkflow directamente o invoca al resto vía POST.
          </p>
        </div>
        <div className="rounded-lg border border-gray-800 bg-[#111111] px-4 py-3 text-sm text-gray-300">
          {workflows.length} flujos
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
            partial: 'parcial',
            descriptive: 'descriptivo',
          };

          return (
            <div key={workflow.name} className="rounded-lg border border-gray-800 bg-[#111111] p-5">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Layers className="h-5 w-5 text-teal-300" />
                <span className="font-semibold text-gray-100">{workflow.name}</span>
                <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${statusStyles[status]}`}>
                  {statusLabels[status]}
                </span>
                <span className="rounded-full border border-gray-700 bg-gray-900 px-2 py-0.5 text-xs text-gray-400">
                  entrada: {workflow.input}
                </span>
              </div>
              {workflow.truth ? (
                <p className="mb-3 text-xs leading-5 text-gray-500">{workflow.truth}</p>
              ) : null}

              <div className="mb-4 space-y-1">
                {workflow.steps.map((step, index) => (
                  <div key={`${workflow.name}-${index}`} className="flex items-start gap-2 text-xs">
                    <span className="mt-0.5 font-mono text-teal-300/60">{String(index + 1).padStart(2, '0')}</span>
                    <span className="font-mono text-gray-400">{step}</span>
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between gap-3 border-t border-gray-800 pt-3">
                <div className="flex items-center gap-1.5 text-xs text-gray-500">
                  {status === 'implemented'
                    ? 'Ejecutable vía POST /run'
                    : status === 'partial'
                      ? 'Ejecución parcial vía POST /run'
                      : 'Sin ejecución vía API (scheduler/Dramatiq)'}
                </div>
                {isGenerateThesis ? (
                  <MutationForm action={runWorkflow} className="flex items-center gap-2" successMessage="Flujo ejecutado">
                    <input name="workflow" type="hidden" value={workflow.name} />
                    {needsTicker && (
                      <Input
                        className="h-8 w-28 border-gray-700 bg-black/30 text-gray-200 text-sm"
                        name="ticker"
                        placeholder="MSFT"
                        required
                      />
                    )}
                    <Button size="sm" type="submit" variant="outline">
                      <Play className="h-3.5 w-3.5" />
                      Ejecutar
                    </Button>
                  </MutationForm>
                ) : (
                  <span className="text-xs text-gray-600">
                    POST /api/workflows/{workflow.name}/run
                  </span>
                )}
              </div>
            </div>
          );
        })}
        {!workflows.length ? (
          <div className="col-span-2 rounded-lg border border-gray-800 bg-[#111111] p-5 text-sm text-gray-500">
            Sin flujos registrados. Verifica que el backend Python esté corriendo.
          </div>
        ) : null}
      </section>
    </main>
  );
}

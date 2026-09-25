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
import BackendOffline from '@/components/system/BackendOffline';
import { SubmitButton } from '@/components/screeners/SubmitButton';
import { isBackendUnavailableError } from '@/lib/backend-offline';
import { getErrorMessage } from '@/lib/types/errors';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type PageProps = { searchParams: Promise<{ left?: string; operator?: string; right?: string; ranking?: string; direction?: string }> };
const operators: ScreenCriterion['operator'][] = ['>', '>=', '<', '<=', '==', '!='];

function Results({ result }: { result: ScreenResult }) {
  const newMatches = new Set(result.new_match_company_ids ?? []);
  return (
    <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center"><div><h2 className="text-lg font-semibold text-gray-100">Resultados del filtro</h2><p className="text-sm text-gray-500">{result.match_count} coincidencias en {result.company_count} empresas</p></div>{result.ranking_formula ? <Badge className="md:ml-auto" variant="outline">ranking: {result.ranking_formula} · {result.ranking_direction}</Badge> : null}</div>
      <div className="overflow-x-auto"><table className="w-full min-w-[980px] text-left text-sm"><thead className="text-xs uppercase text-gray-500"><tr><th className="border-b border-gray-800 py-2">Empresa</th><th className="border-b border-gray-800 py-2">Coincidencia</th><th className="border-b border-gray-800 py-2 text-right">Ranking</th><th className="border-b border-gray-800 py-2 text-right">Cobertura</th><th className="border-b border-gray-800 py-2 text-right">Confianza</th><th className="border-b border-gray-800 py-2">Últimos datos</th><th className="border-b border-gray-800 py-2">Faltantes</th></tr></thead><tbody>
        {result.results.map((row) => <tr className="border-b border-gray-900" key={row.company_id}><td className="py-3"><Link className="font-semibold text-teal-300 hover:text-teal-200" href={`/research/${row.ticker}`}>{row.ticker}</Link><div className="text-xs text-gray-500">{row.name}</div></td><td className="py-3"><div className="flex gap-2"><Badge className={row.matched ? 'border-teal-800 text-teal-300' : 'border-gray-700 text-gray-400'} variant="outline">{row.matched ? 'coincidencia' : 'sin coincidencia'}</Badge>{newMatches.has(row.company_id) ? <Badge>nuevo</Badge> : null}</div></td><td className="py-3 text-right text-gray-300">{row.rank_value ?? 's/d'}</td><td className="py-3 text-right text-gray-300">{row.coverage_percent.toFixed(0)}%</td><td className="py-3 text-right text-gray-300">{(Number(row.confidence) * 100).toFixed(0)}%</td><td className="py-3 text-gray-500">{row.latest_data_at ?? 's/d'}</td><td className="py-3 text-amber-300">{row.missing_fields.join(', ') || '—'}</td></tr>)}
      </tbody></table></div>
    </section>
  );
}

export default async function ScreenersPage({ searchParams }: PageProps) {
  const query = await searchParams;
  const operator = operators.includes(query.operator as ScreenCriterion['operator']) ? query.operator as ScreenCriterion['operator'] : '>=';
  let workspace: Awaited<ReturnType<typeof getScreenerWorkspace>>;
  try {
    workspace = await getScreenerWorkspace();
  } catch (error) {
    if (isBackendUnavailableError(error)) {
      return <BackendOffline feature="Screeners" retryHref="/screeners" />;
    }
    throw error;
  }
  const { metrics, screens } = workspace;

  // El screener ad-hoc con fórmula inválida debe mostrar el error en un
  // banner visible en español, nunca escalar al boundary global.
  let result: ScreenResult | null = null;
  let screenError: string | null = null;
  try {
    result = await runAdHocScreen({
      left: query.left ?? '',
      operator,
      right: query.right ?? '',
      rankingFormula: query.ranking,
      rankingDirection: query.direction === 'asc' ? 'asc' : 'desc',
    });
  } catch (error) {
    if (isBackendUnavailableError(error)) {
      return <BackendOffline feature="Screeners" retryHref="/screeners" />;
    }
    screenError = getErrorMessage(error) || 'La fórmula del screener no es válida. Revisa la sintaxis y reintenta.';
  }

  return (
    <main id="content" tabIndex={-1} className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="border-b border-gray-800 pb-5"><p className="text-sm font-semibold uppercase text-teal-300">Descubrimiento de empresas</p><h1 className="mt-1 text-3xl font-bold text-gray-100">Screeners</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">Construye fórmulas seguras, evalúa cobertura y confianza, guarda filtros e identifica nuevas coincidencias.</p></header>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <form className="rounded-xl border border-gray-800 bg-[#101010] p-5" method="get">
          <div className="mb-4 flex items-center gap-2"><Filter className="h-5 w-5 text-teal-300" /><h2 className="font-semibold text-gray-100">Ejecutar un filtro ad-hoc</h2></div>
          <div className="grid gap-3 md:grid-cols-[1fr_110px_1fr]"><Input defaultValue={query.left} name="left" placeholder="roic - wacc" required /><select className="h-9 rounded-md border border-gray-800 bg-black px-3 text-sm text-gray-200" defaultValue={operator} name="operator">{operators.map((item) => <option key={item}>{item}</option>)}</select><Input defaultValue={query.right} name="right" placeholder="0" required /></div>
          <div className="mt-3 grid gap-3 md:grid-cols-[1fr_180px_auto]"><Input defaultValue={query.ranking} name="ranking" placeholder="Fórmula de ranking (opcional)" /><select className="h-9 rounded-md border border-gray-800 bg-black px-3 text-sm text-gray-200" defaultValue={query.direction ?? 'desc'} name="direction"><option value="desc">Mayor primero</option><option value="asc">Menor primero</option></select><SubmitButton /></div>
                    <p className="mt-3 text-xs text-gray-500">Permitidos: números, nombres de métricas, aritmética, min, max y abs. No se ejecuta código arbitrario.</p>
        </form>

        <MutationForm action={createCustomMetric} className="rounded-xl border border-gray-800 bg-[#101010] p-5" resetOnSuccess successMessage="Métrica personalizada guardada">
          <div className="mb-4 flex items-center gap-2"><Calculator className="h-5 w-5 text-teal-300" /><h2 className="font-semibold text-gray-100">Métrica personalizada</h2></div>
          <div className="grid gap-3 sm:grid-cols-2"><Input name="metric_key" placeholder="roic_spread" required /><Input name="name" placeholder="Diferencial ROIC" required /><Input className="sm:col-span-2" name="formula" placeholder="roic - wacc" required /><Input name="unit" defaultValue="decimal" /><Input name="description" placeholder="Definición" /><Button className="w-fit" type="submit">Guardar métrica</Button></div>
        </MutationForm>
      </section>

      {screenError ? (
        <div className="rounded-xl border border-red-800 bg-red-950/40 p-4 text-sm text-red-200" role="alert">
          <p className="font-semibold">No se pudo ejecutar el screener.</p>
          <p className="mt-1">{screenError}</p>
        </div>
      ) : null}
      {result ? <Results result={result} /> : null}

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <MutationForm action={createSavedScreen} className="rounded-xl border border-gray-800 bg-[#101010] p-5" resetOnSuccess successMessage="Filtro guardado">
          <div className="mb-4 flex items-center gap-2"><Save className="h-5 w-5 text-teal-300" /><h2 className="font-semibold text-gray-100">Constructor visual de filtros</h2></div>
          <div className="grid gap-3 sm:grid-cols-2"><Input name="name" placeholder="Calidad a precio razonable" required /><Input name="description" placeholder="Propósito y universo" /></div>
          {([['', true], ['_2', false], ['_3', false]] as const).map(([suffix, required]) => <div className="mt-3 grid gap-3 md:grid-cols-[1fr_110px_1fr]" key={suffix || 'one'}><Input name={`left${suffix}`} placeholder={suffix ? 'Fórmula opcional' : 'roic'} required={required} /><select className="h-9 rounded-md border border-gray-800 bg-black px-3 text-sm text-gray-200" name={`operator${suffix}`} defaultValue={'>='}>{operators.map((item) => <option key={item}>{item}</option>)}</select><Input name={`right${suffix}`} placeholder={suffix ? 'Umbral opcional' : 'wacc'} required={required} /></div>)}
          <div className="mt-3 grid gap-3 sm:grid-cols-2"><Input name="ranking_formula" placeholder="free_cash_flow / market_cap" /><select className="h-9 rounded-md border border-gray-800 bg-black px-3 text-sm text-gray-200" name="ranking_direction" defaultValue="desc"><option value="desc">Mayor primero</option><option value="asc">Menor primero</option></select></div>
          <label className="mt-4 flex items-center gap-2 text-sm text-gray-300"><input defaultChecked name="alerts_enabled" type="checkbox" />Avisar de nuevas coincidencias</label>
          <Button className="mt-4" type="submit"><Save className="h-4 w-4" />Guardar filtro</Button>
        </MutationForm>

        <section className="rounded-xl border border-gray-800 bg-[#101010] p-5"><h2 className="font-semibold text-gray-100">Filtros guardados</h2><div className="mt-4 grid gap-3">{screens.map((screen) => <article className="rounded-lg border border-gray-800 bg-black/30 p-4" key={screen.id}><div className="flex items-start gap-3"><div><h3 className="font-semibold text-gray-200">{screen.name}</h3><p className="mt-1 text-xs text-gray-500">{screen.criteria.length} criterios · {screen.alerts_enabled ? 'alertas activadas' : 'alertas desactivadas'} · última {screen.last_run_at ?? 'nunca'}</p></div><Button asChild className="ml-auto" size="sm"><Link href={`/screeners/${screen.id}`}><Play className="h-4 w-4" />Ejecutar</Link></Button></div>{screen.description ? <p className="mt-3 text-sm text-gray-400">{screen.description}</p> : null}</article>)}{!screens.length ? <p className="text-sm text-gray-500">Aún no hay filtros guardados.</p> : null}</div></section>
      </section>

      <section className="rounded-xl border border-gray-800 bg-[#101010] p-5"><h2 className="font-semibold text-gray-100">Métricas personalizadas activas</h2><div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{metrics.map((metric) => <article className="rounded-lg border border-gray-800 bg-black/30 p-4" key={metric.id}><div className="flex items-center justify-between gap-3"><span className="font-semibold text-gray-200">{metric.name}</span><Badge variant="outline">v{metric.version}</Badge></div><code className="mt-3 block text-sm text-teal-300">{metric.metric_key} = {metric.formula}</code><p className="mt-2 text-xs text-gray-500">{metric.unit} · {metric.description || 'Sin descripción'}</p></article>)}{!metrics.length ? <p className="text-sm text-gray-500">Aún no hay métricas personalizadas.</p> : null}</div></section>
    </main>
  );
}

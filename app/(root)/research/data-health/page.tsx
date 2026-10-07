import Link from 'next/link';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { getDataHealth } from '@/lib/actions/data-health.actions';
import { formatNumber, formatUserDateTime } from '@/lib/format';
import { PageHeader } from '@/components/ui/page-header';
import { Panel } from '@/components/ui/panel';

export const dynamic = 'force-dynamic';
const labels: Record<string, string> = { available: 'Datos almacenados', stale: 'Datos antiguos', empty: 'Sin datos', error: 'Error de lectura', degraded: 'Consulta fallida', observed: 'Consulta registrada' };
const stamp = (value: string | null) => value ? formatUserDateTime(value) : 'N/D';
const PAGE_SIZE = 12;

export default async function DataHealthPage({ searchParams }: { searchParams: Promise<{ page?: string; connectors?: string }> }) {
  await requireAuthenticatedUser();
  const query = await searchParams;
  const data = await getDataHealth().catch(() => null);
  const totalPages = Math.max(1, Math.ceil((data?.sources.length ?? 0) / PAGE_SIZE));
  const connectorPages = Math.max(1, Math.ceil((data?.connectors.length ?? 0) / PAGE_SIZE));
  const connectorPage = Math.min(connectorPages, Math.max(1, Number.parseInt(query.connectors ?? '1', 10) || 1));
  const page = Math.min(totalPages, Math.max(1, Number.parseInt(query.page ?? '1', 10) || 1));
  return <main id="content" tabIndex={-1} className="mx-auto flex max-w-7xl flex-col gap-6">
    <PageHeader title="Salud de los datos" back={<Link href="/research" className="text-teal-300">Research</Link>} />
    {!data ? <Panel title="Error de lectura"><p>No se pudo leer el inventario. No se puede afirmar que las fuentes estén caídas ni que la cobertura sea cero.</p><Link className="text-teal-300" href="/research/data-health">Reintentar</Link></Panel> : <>
      <Panel title="Cobertura almacenada">
        <p className="mb-2 text-sm text-gray-400">{data.coverage_basis}</p>
        <p className="mb-4 text-sm text-gray-400">{data.freshness_basis} Corte: {stamp(data.as_of)}. Caché: 60 s.</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.sources.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((row, index) => <article key={`${row.layer}-${row.source}-${index}`} className="rounded-lg border border-gray-800 p-4">
            <h2 className="font-semibold">{row.layer} · {row.source ?? 'Sin fuente'}</h2>
            <p className={['error', 'stale'].includes(row.status) ? 'text-amber-300' : 'text-gray-400'}>{labels[row.status] ?? 'N/D'}</p>
            <p className="mt-3 text-2xl">{row.coverage_pct === null ? 'N/D' : `${formatNumber(row.coverage_pct, { maximumFractionDigits: 1 })}%`}</p>
            <p className="text-xs text-gray-400">DERIVADO · {row.covered === null ? 'N/D' : formatNumber(row.covered, { maximumFractionDigits: 0 })} / {formatNumber(row.total, { maximumFractionDigits: 0 })} empresas</p>
            <p className="mt-2 text-sm">Última escritura: {stamp(row.last_update)}</p>
            {row.max_age_days !== null && <p className="text-xs text-gray-500">Límite del panel: {row.max_age_days} días sin escritura</p>}
            {row.reason && <p className="mt-2 text-sm text-amber-300">{row.reason}</p>}
          </article>)}
        </div>
        <nav aria-label="Páginas del inventario" className="mt-4 flex items-center gap-4">
          {page > 1 && <Link href={`/research/data-health?page=${page - 1}`} className="text-teal-300">Anterior</Link>}
          <span>{page} / {totalPages}</span>
          {page < totalPages && <Link href={`/research/data-health?page=${page + 1}`} className="text-teal-300">Siguiente</Link>}
        </nav>
      </Panel>
      <Panel title="Consultas registradas">
        <p className="mb-3 text-sm text-gray-400">No todos los conectores registran sus consultas. Sin registro no significa caído.</p>
        {!data.connectors.length ? <p>Sin registro de consultas.</p> : <details><summary className="cursor-pointer text-teal-300">Ver {data.connectors.length} registros</summary><ul className="mt-3 grid gap-2 sm:grid-cols-2">{data.connectors.slice((connectorPage - 1) * PAGE_SIZE, connectorPage * PAGE_SIZE).map((row, i) => <li className="rounded border border-gray-800 p-3 text-sm" key={`${row.source}-${i}`}>{row.source} · {labels[row.status] ?? 'N/D'}<br />Último éxito: {stamp(row.last_success)}<br />Último intento: {stamp(row.last_attempt)}{row.errors !== null && row.errors > 0 && <p className="text-amber-300">{row.errors} fallos consecutivos</p>}</li>)}</ul><nav aria-label="Páginas de consultas" className="mt-4 flex gap-4">{connectorPage > 1 && <Link className="text-teal-300" href={`?page=${page}&connectors=${connectorPage - 1}`}>Anterior</Link>}<span>{connectorPage} / {connectorPages}</span>{connectorPage < connectorPages && <Link className="text-teal-300" href={`?page=${page}&connectors=${connectorPage + 1}`}>Siguiente</Link>}</nav></details>}
      </Panel>
    </>}
  </main>;
}

import Link from 'next/link';

import type { AstOrbitOverview } from '@/lib/actions/asts-orbits.actions';
import { formatNumber, formatUserDateTime } from '@/lib/format';
import { Panel } from '@/components/ui/panel';

export function AstOrbitPanel({ data }: { data: AstOrbitOverview | null }) {
  return <div className="space-y-5">
    <Panel title="Órbitas de la constelación AST" description="Semieje mayor estimado a partir de elementos orbitales públicos, no telemetría del satélite.">
      <p className="text-sm leading-6 text-gray-300">{data?.usage_note ?? 'La lectura orbital no está disponible ahora. No inferimos órbitas ni despliegues sin elementos vigentes.'}</p>
      <p className="mt-3 text-xs text-gray-500">Fuente: {data?.source ?? 'CelesTrak'} · descarga cada {data?.cadence_hours ?? 6} h · última descarga: {data?.fetched_at ? formatUserDateTime(data.fetched_at) : 'sin datos'}. La fecha orbital de cada objeto se muestra aparte.</p>
      {data?.source_url ? <a className="mt-2 inline-block break-all text-xs text-teal-300 hover:underline" href={data.source_url} rel="noopener noreferrer" target="_blank">Ver catálogo en CelesTrak</a> : null}
    </Panel>
    {data?.status === 'disponible' && data.objects.length ? <ul className="grid min-w-0 gap-3 lg:grid-cols-2">
      {data.objects.map((item) => <li className="min-w-0 rounded-xl border border-gray-800 bg-[#101010] p-4" key={item.norad_cat_id}>
        <div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="break-words font-semibold text-gray-100">{item.object_name}</h3><span className="text-xs text-gray-500">NORAD {item.norad_cat_id}</span></div>
        <p className="mt-2 text-sm text-gray-300">Semieje mayor: {item.sma_km === null ? 'sin datos' : `${formatNumber(item.sma_km, { maximumFractionDigits: 1 })} km`}</p>
        <p className="mt-1 text-sm text-gray-300">Tendencia: {item.signal.delta_sma_km === null ? 'sin historial comparable' : `${item.signal.delta_sma_km > 0 ? '+' : ''}${formatNumber(item.signal.delta_sma_km, { maximumFractionDigits: 2 })} km en ${formatNumber(item.signal.hours, { maximumFractionDigits: 0 })} h`}</p>
        <p className="mt-1 text-sm text-amber-300">{item.signal.status}</p>
        <p className="mt-2 text-xs text-gray-500">Época orbital: {formatUserDateTime(item.epoch)} · {item.history.length} observaciones guardadas</p>
        <details className="mt-3"><summary className="min-h-11 cursor-pointer py-3 text-sm text-teal-300">Ver historial orbital</summary><div className="max-h-52 overflow-auto rounded-md border border-gray-800 p-2 text-xs text-gray-300">{item.history.length ? item.history.map((sample) => <p className="flex flex-wrap justify-between gap-2 border-b border-gray-800 py-2 last:border-0" key={sample.epoch}><span>{formatUserDateTime(sample.epoch)}</span><span>{formatNumber(sample.sma_km, { maximumFractionDigits: 1 })} km</span></p>) : <p>Sin historial.</p>}</div></details>
      </li>)}
    </ul> : <Panel title="Objetos"><p className="text-sm text-gray-400">Sin datos orbitales vigentes. El catálogo deja de publicarse tras 30 h sin una descarga válida; no se reutiliza un dato caducado.</p></Panel>}
    <p className="text-xs leading-5 text-gray-500">Una firma compatible con variación orbital solo invita a revisar fuentes independientes. No confirma despliegue, maniobra ni posición actual.</p>
    <Link className="text-sm text-teal-300 hover:underline" href="/metodologia">Ver método y límites del cálculo</Link>
  </div>;
}

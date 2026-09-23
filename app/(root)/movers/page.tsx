import Link from 'next/link';
import { TrendingDown, TrendingUp, Activity } from 'lucide-react';

import { getMarketMovers, type MarketMover } from '@/lib/actions/market.actions';
import BackendOffline from '@/components/system/BackendOffline';
import { isBackendUnavailableError } from '@/lib/backend-offline';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

function formatPct(value: number): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)} %`;
}

function MoversTable({ rows, caption }: { rows: MarketMover[]; caption: string }) {
  if (!rows.length) {
    return <p className="text-sm text-gray-500">Sin datos todavía — en cuanto haya precios registrados aparecerán aquí.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="text-xs uppercase text-gray-500">
          <tr>
            <th className="border-b border-gray-800 py-2" scope="col">Empresa</th>
            <th className="border-b border-gray-800 py-2 text-right" scope="col">Precio</th>
            <th className="border-b border-gray-800 py-2 text-right" scope="col">Cambio</th>
            <th className="border-b border-gray-800 py-2 text-right" scope="col">Volumen</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr className="border-b border-gray-900" key={row.ticker}>
              <td className="py-3">
                <Link className="font-semibold text-teal-300 hover:text-teal-200" href={`/research/${row.ticker}`}>
                  {row.ticker}
                </Link>
                <div className="text-xs text-gray-500">{row.name}</div>
              </td>
              <td className="py-3 text-right text-gray-300">{row.price.toFixed(2)}</td>
              <td className={`py-3 text-right font-medium ${row.change_pct >= 0 ? 'text-teal-300' : 'text-red-400'}`}>
                {formatPct(row.change_pct)}
              </td>
              <td className="py-3 text-right text-gray-400">{row.volume.toLocaleString('es-ES')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function MoversPage() {
  let movers;
  try {
    movers = await getMarketMovers(10);
  } catch (error) {
    if (isBackendUnavailableError(error)) {
      return <BackendOffline feature="Movers" retryHref="/movers" />;
    }
    throw error;
  }

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="border-b border-gray-800 pb-5">
        <p className="text-sm font-semibold uppercase text-teal-300">Mercado</p>
        <h1 className="mt-1 text-3xl font-bold text-gray-100">Movers</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
          Subidas, bajadas y más activas calculadas con los precios registrados en tu base de datos
          (último cierre frente al anterior).
          {movers.as_of ? ` Datos del ${movers.as_of}.` : ' Aún no hay precios registrados.'}
        </p>
      </header>

      {movers.universe === 0 ? (
        <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
          <h2 className="font-semibold text-gray-100">Sin movimientos todavía</h2>
          <p className="mt-2 text-sm text-gray-400">
            Esta página se llena sola cuando el refresco de mercado guarde precios.
            Mientras tanto puedes explorar los <Link className="text-teal-300 hover:text-teal-200" href="/screeners">screeners</Link> o
            tu <Link className="text-teal-300 hover:text-teal-200" href="/watchlist">watchlist</Link>.
          </p>
        </section>
      ) : (
        <div className="grid gap-6 xl:grid-cols-3 md:grid-cols-1">
          <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
            <div className="mb-4 flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-teal-300" />
              <h2 className="font-semibold text-gray-100">Subidas</h2>
            </div>
            <MoversTable rows={movers.gainers} caption="Mayores subidas" />
          </section>

          <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
            <div className="mb-4 flex items-center gap-2">
              <TrendingDown className="h-5 w-5 text-red-400" />
              <h2 className="font-semibold text-gray-100">Bajadas</h2>
            </div>
            <MoversTable rows={movers.losers} caption="Mayores bajadas" />
          </section>

          <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
            <div className="mb-4 flex items-center gap-2">
              <Activity className="h-5 w-5 text-teal-300" />
              <h2 className="font-semibold text-gray-100">Más activas</h2>
            </div>
            <MoversTable rows={movers.most_active} caption="Mayor volumen" />
          </section>
        </div>
      )}
    </main>
  );
}

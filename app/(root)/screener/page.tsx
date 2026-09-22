import { getMarketIndices } from '@/lib/actions/market.actions';
import { getScreenerStocksReal } from '@/lib/actions/screener.actions';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import FollowButton from '@/components/screener/FollowButton';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const SECTORES = ['Technology', 'Health Care', 'Financial Services', 'Consumer Cyclical', 'Energy', 'Utilities'];

export default async function ScreenerPage({ searchParams }: { searchParams?: Promise<{ sector?: string }> }) {
  const sector = (await searchParams)?.sector ?? 'Technology';
  // Screener (backend) e índices (backend) son independientes: en paralelo
  // en vez de en serie.
  const [rows, indices] = await Promise.all([
    getScreenerStocksReal({ sector, limit: 25 }).catch(() => []),
    getMarketIndices().catch(() => []),
  ]);

  return (
    <div className="mx-auto w-full max-w-full min-w-0 space-y-6 overflow-x-clip p-4 sm:p-6">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold break-words text-gray-100">Screener</h1>
        <p className="mt-1 text-sm text-gray-400">Large caps líquidos con precio y market cap reales (motor de análisis, caché 60s)</p>
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar por sector">
        {SECTORES.map((s) => (
          <Button key={s} asChild variant={sector === s ? 'default' : 'outline'} size="sm" className="min-h-[44px] min-w-[44px] rounded-md px-4">
            <Link href={`/screener?sector=${encodeURIComponent(s)}`}>{s}</Link>
          </Button>
        ))}
      </div>

      <div className="grid min-w-0 grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="min-w-0 border-gray-800 lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base break-words">Oportunidades — {sector}</CardTitle>
          </CardHeader>
          <CardContent className="min-w-0 px-3 sm:px-6">
            {rows.length === 0 ? (
              <div className="px-4 py-10 text-center">
                <p className="text-sm text-gray-500 sm:text-base">
                  No hay datos ahora mismo — el backend puede estar arrancando. Reintenta en 30s.
                </p>
                <Button asChild variant="outline" className="mt-4 min-h-[44px] px-5">
                  <Link href={`/screener?sector=${encodeURIComponent(sector)}`}>Reintentar</Link>
                </Button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                {/*
                  Misma <table> en el DOM en todos los viewports (accesibilidad y
                  tests): en <md las filas se muestran como cards apiladas
                  (display block + etiquetas por celda) y desde md como tabla.
                */}
                <table className="w-full text-sm">
                  <thead className="hidden md:table-header-group">
                    <tr className="border-b border-gray-800 text-left text-gray-400">
                      <th className="pb-3 pr-4">Ticker</th>
                      <th className="pb-3 pr-4">Nombre</th>
                      <th className="pb-3 pr-4 text-right">Precio</th>
                      <th className="pb-3 pr-4 text-right">Cambio sesión</th>
                      <th className="pb-3 pr-4 text-right">Market Cap</th>
                      <th className="pb-3 text-right">Seguir</th>
                    </tr>
                  </thead>
                  <tbody className="block space-y-3 md:table-row-group md:space-y-0">
                    {rows.map((r) => (
                      <tr key={r.symbol} className="block rounded-xl border border-gray-800 bg-gray-900/40 p-4 hover:bg-gray-800/30 md:table-row md:rounded-none md:border-0 md:border-b md:border-gray-800/60 md:bg-transparent md:p-0 md:last:border-0">
                        <td className="flex items-center justify-between gap-3 py-1 md:table-cell md:py-3 md:pr-4">
                          <span className="text-xs text-gray-500 md:hidden">Ticker</span>
                          <Link
                            href={`/research/${r.symbol}`}
                            prefetch
                            className="inline-flex min-h-[44px] items-center font-semibold text-teal-300 hover:text-teal-200"
                          >
                            {r.symbol}
                          </Link>
                        </td>
                        <td className="flex items-center justify-between gap-3 py-1 md:table-cell md:py-3 md:pr-4">
                          <span className="shrink-0 text-xs text-gray-500 md:hidden">Nombre</span>
                          <Link href={`/research/${r.symbol}`} prefetch className="max-w-[180px] truncate text-right text-gray-300 hover:text-teal-200 md:max-w-[220px] md:text-left" title={r.name}>{r.name}</Link>
                        </td>
                        <td className="flex items-center justify-between gap-3 py-1 md:table-cell md:py-3 md:pr-4 md:text-right">
                          <span className="text-xs text-gray-500 md:hidden">Precio</span>
                          <span className="font-semibold text-gray-200">${r.price.toFixed(2)}</span>
                        </td>
                        <td className="flex items-center justify-between gap-3 py-1 md:table-cell md:py-3 md:pr-4 md:text-right">
                          <span className="text-xs text-gray-500 md:hidden">Cambio sesión</span>
                          <span className={`font-mono ${r.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {r.changePercent >= 0 ? '+' : ''}{r.changePercent.toFixed(2)}%
                          </span>
                        </td>
                        <td className="flex items-center justify-between gap-3 py-1 md:table-cell md:py-3 md:pr-4 md:text-right">
                          <span className="text-xs text-gray-500 md:hidden">Market Cap</span>
                          <span className="font-mono text-gray-300">${(r.marketCap / 1e9).toFixed(1)}B</span>
                        </td>
                        <td className="mt-2 flex items-center justify-between gap-3 border-t border-gray-800/60 pt-3 md:table-cell md:mt-0 md:border-0 md:py-3 md:pt-3 md:text-right">
                          <span className="text-xs text-gray-500 md:hidden">Seguir</span>
                          <FollowButton symbol={r.symbol} company={r.name} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="min-w-0 border-gray-800">
          <CardHeader>
            <CardTitle className="text-base">Índices y macro</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {indices.map((i) => (
                <div key={i.symbol} className="flex min-w-0 items-center justify-between gap-3">
                  <span className="min-w-0 flex-1 truncate text-gray-300">{i.name}</span>
                  <span className="shrink-0 font-semibold text-gray-100">${i.price.toFixed(2)}</span>
                </div>
              ))}
              {indices.length === 0 && <p className="text-sm text-gray-500">Sin datos de índices</p>}
            </div>
            <p className="mt-4 text-xs text-gray-500">S&amp;P 500, Nasdaq, Bitcoin, Oro, Plata — valores reales.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

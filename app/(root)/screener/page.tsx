import { getMarketIndices } from '@/lib/actions/market.actions';
import { getScreenerStocksReal } from '@/lib/actions/screener.actions';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import FollowButton from '@/components/screener/FollowButton';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const SECTORES = ['Technology', 'Health Care', 'Financial Services', 'Consumer Cyclical', 'Energy', 'Utilities'];

export default async function ScreenerPage({ searchParams }: { searchParams?: { sector?: string } }) {
  const sector = searchParams?.sector ?? 'Technology';
  const rows = await getScreenerStocksReal({ sector, limit: 25 }).catch(() => []);
  const indices = await getMarketIndices().catch(() => []);

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-100">Screener</h1>
        <p className="text-sm text-gray-400 mt-1">Large caps líquidos con precios y market caps reales (Finnhub, caché 60s)</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {SECTORES.map((s) => (
          <Button key={s} asChild variant={sector === s ? 'default' : 'outline'} size="sm" className="rounded-md">
            <Link href={`/screener?sector=${encodeURIComponent(s)}`}>{s}</Link>
          </Button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 border-gray-800">
          <CardHeader>
            <CardTitle className="text-base">Oportunidades — {sector}</CardTitle>
          </CardHeader>
          <CardContent>
            {rows.length === 0 ? (
              <div className="py-10 text-center text-gray-500">
                No hay datos ahora mismo — el backend puede estar arrancando. Reintenta en 30s.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-400 border-b border-gray-800">
                      <th className="pb-3 pr-4">Ticker</th>
                      <th className="pb-3 pr-4">Nombre</th>
                      <th className="pb-3 pr-4 text-right">Precio</th>
                      <th className="pb-3 pr-4 text-right">Cambio sesión</th>
                      <th className="pb-3 pr-4 text-right">Market Cap</th>
                      <th className="pb-3 text-right">Seguir</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.symbol} className="border-b border-gray-800/60 last:border-0 hover:bg-gray-800/30">
                        <td className="py-3 pr-4 font-semibold text-gray-100">
                          <Link href={`/stocks/${r.symbol}`} prefetch className="text-teal-300 hover:text-teal-200">{r.symbol}</Link>
                        </td>
                        <td className="py-3 pr-4 text-gray-300 max-w-[220px] truncate" title={r.name}>{r.name}</td>
                        <td className="py-3 pr-4 text-right text-gray-200">${r.price.toFixed(2)}</td>
                        <td className={`py-3 pr-4 text-right ${r.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {r.changePercent >= 0 ? '+' : ''}{r.changePercent.toFixed(2)}%
                        </td>
                        <td className="py-3 pr-4 text-right text-gray-300">
                          ${(r.marketCap / 1e9).toFixed(1)}B
                        </td>
                        <td className="py-3 text-right">
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

        <Card className="border-gray-800">
          <CardHeader>
            <CardTitle className="text-base">Índices y macro</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {indices.map((i) => (
                <div key={i.symbol} className="flex items-center justify-between">
                  <span className="text-gray-300">{i.name}</span>
                  <span className="text-gray-100 font-semibold">${i.price.toFixed(2)}</span>
                </div>
              ))}
              {indices.length === 0 && <p className="text-sm text-gray-500">Sin datos de índices</p>}
            </div>
            <p className="mt-4 text-xs text-gray-500">S&P 500, Nasdaq, Bitcoin, Oro, Plata — valores reales.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
import type { Metadata } from 'next';
import { getMarketIndices } from '@/lib/actions/market.actions';
import { getSavedScreenerEngines, getScreenerStocksReal } from '@/lib/actions/screener.actions';
import { formatCompact, formatPercent, formatPrice } from '@/lib/format';
import { etiquetaSector } from '@/lib/labels';
import { t } from '@/lib/i18n/t';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';
import { RefreshCcw } from 'lucide-react';
import FollowButton from '@/components/screener/FollowButton';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'Screener',
  description:
    'Large caps líquidos con precio y market cap reales, filtros guardados del motor de análisis y lectura offline con Finnhub.',
};

/** Sectores que el Screener ofrece: etiqueta ES de lib/labels.ts + valor EN
 *  que espera el backend. */
const SECTORES = [
  { en: 'Technology' },
  { en: 'Health Care' },
  { en: 'Financial Services' },
  { en: 'Consumer Cyclical' },
  { en: 'Energy' },
  { en: 'Utilities' },
];

const sectorEn = (value: string) =>
  SECTORES.some((s) => s.en === value) ? value : 'Technology';

const sectorEs = (value: string) => etiquetaSector(value);

export default async function ScreenerPage({ searchParams }: { searchParams?: Promise<{ sector?: string }> }) {
  const sector = sectorEn((await searchParams)?.sector ?? 'Technology');
  // Screener (backend) e índices (backend) son independientes: en paralelo
  // en vez de en serie. El flag distingue "backend caído" (reintentar) de
  // "filtro sin resultados" (cambiar de sector).
  const [screenerResult, indices, engineScreens] = await Promise.all([
    getScreenerStocksReal({ sector, limit: 25 }).then(
      (rows) => ({ rows, backendDown: false }),
      () => ({ rows: [] as Awaited<ReturnType<typeof getScreenerStocksReal>>, backendDown: true }),
    ),
    getMarketIndices().catch(() => []),
    // Motor de análisis (POST /api/screeners/run ad-hoc y filtros guardados):
    // si cae, la tabla Finnhub de abajo queda como lectura offline.
    getSavedScreenerEngines().then(
      (screens) => ({ screens, engineDown: false }),
      () => ({ screens: [] as Awaited<ReturnType<typeof getSavedScreenerEngines>>, engineDown: true }),
    ),
  ]);
  const { rows, backendDown } = screenerResult;

  return (
    <main id="content" tabIndex={-1} className="mx-auto w-full max-w-full min-w-0 space-y-6 overflow-x-clip p-4 sm:p-6">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold break-words text-gray-100">{t('nav.screener')}</h1>
        <p className="mt-1 text-sm text-gray-400">Large caps líquidos con precio y market cap reales (motor de análisis, caché 60s)</p>
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar por sector">
        {SECTORES.map((s) => (
          <Button key={s.en} asChild variant={sector === s.en ? 'default' : 'outline'} size="sm" className="min-h-[44px] min-w-[44px] rounded-md px-4">
            <Link href={`/screener?sector=${encodeURIComponent(s.en)}`}>{etiquetaSector(s.en)}</Link>
          </Button>
        ))}
      </div>

      <Card className="min-w-0 border-gray-800">
        <CardHeader>
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base break-words">Motor de análisis</CardTitle>
            {engineScreens.engineDown ? (
              <Badge variant="outline">motor no disponible · Finnhub como fallback offline</Badge>
            ) : (
              <Badge>{engineScreens.screens.length} filtros guardados</Badge>
            )}
            <Button asChild variant="outline" size="sm" className="ml-auto">
              <Link href="/screeners">Abrir screeners</Link>
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {engineScreens.engineDown ? (
            <p className="text-sm text-gray-500">
              El motor (POST /api/screeners/run) no responde: la tabla de abajo muestra
              precios Finnhub como lectura offline, sin análisis de cobertura.
            </p>
          ) : engineScreens.screens.length === 0 ? (
            <p className="text-sm text-gray-500">
              Motor operativo pero sin filtros guardados.{' '}
              <Link href="/screeners" className="text-teal-300 hover:text-teal-200 hover:underline">
                Crea el primero en Screeners
              </Link>{' '}
              (filtros ad-hoc y guardados contra métricas trazables).
            </p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {engineScreens.screens.slice(0, 6).map((screen) => (
                <li key={screen.id}>
                  <Button asChild variant="outline" size="sm">
                    <Link href={`/screeners/${screen.id}`}>{screen.name}</Link>
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="grid min-w-0 grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="min-w-0 border-gray-800 lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base break-words">Oportunidades — {sectorEs(sector)}</CardTitle>
          </CardHeader>
          <CardContent className="min-w-0 px-3 sm:px-6">
            {rows.length === 0 ? (
              backendDown ? (
              /* Mismo aspecto y mismo reintento que components/system/BackendOffline.tsx
               * (distintivo ámbar + explicación + botón Reintentar), pero en línea:
               * aquí la página sigue teniendo contenido útil (filtros de sector,
               * índices) y sustituir la tabla por un error a pantalla completa
               * tiraría el H1 y el panel del motor. */
              <div className="px-4 py-10 text-center">
                <span className="inline-block rounded-full border border-amber-900/60 bg-amber-950/40 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-amber-300">
                  Motor de análisis desconectado
                </span>
                <p className="mx-auto mt-4 max-w-md text-sm leading-6 text-gray-400 sm:text-base">
                  No hay datos ahora mismo: el motor no responde y puede estar arrancando. Tus datos
                  están a salvo, reintenta en unos segundos.
                </p>
                <Button asChild className="mt-4 min-h-[44px] px-6">
                  <Link href={`/screener?sector=${encodeURIComponent(sector)}`}>
                    <RefreshCcw aria-hidden="true" className="h-4 w-4" />
                    Reintentar
                  </Link>
                </Button>
                <p className="mt-4 text-xs text-gray-500">
                  Si el problema persiste, el backend local no está en marcha.
                </p>
              </div>
              ) : (
              /* Distinto del anterior: aquí el motor responde y el filtro no tiene
               * coincidencias. No se ofrece "Reintentar" porque repetir la misma
               * consulta daría el mismo vacío: la acción es cambiar de sector. */
              <div className="px-4 py-10 text-center">
                <p className="text-sm text-gray-500 sm:text-base">
                  Sin resultados para {sectorEs(sector)} con este filtro. Prueba con otro sector.
                </p>
              </div>
              )
            ) : (
              <div aria-label="Oportunidades por sector" className="overflow-x-auto" role="region" tabIndex={0}>
                {/*
                  Misma <table> en el DOM en todos los viewports (accesibilidad y
                  tests): en <md las filas se muestran como cards apiladas
                  (display block + etiquetas por celda) y desde md como tabla.
                */}
                <table className="w-full text-sm">
                  <caption className="sr-only">Oportunidades del screener por sector: ticker, nombre, precio, cambio de sesión, market cap y acción de seguir</caption>
                  <thead className="hidden md:table-header-group">
                    <tr className="border-b border-gray-800 text-left text-gray-400">
                      <th className="pb-3 pr-4" scope="col">Ticker</th>
                      <th className="pb-3 pr-4" scope="col">Nombre</th>
                      <th className="pb-3 pr-4 text-right" scope="col">Precio</th>
                      <th className="pb-3 pr-4 text-right" scope="col">Cambio sesión</th>
                      <th className="pb-3 pr-4 text-right" scope="col">Market Cap</th>
                      <th className="pb-3 text-right" scope="col">Seguir</th>
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
                          <span className="font-semibold text-gray-200">{formatPrice(r.price, 'USD')}</span>
                        </td>
                        <td className="flex items-center justify-between gap-3 py-1 md:table-cell md:py-3 md:pr-4 md:text-right">
                          <span className="text-xs text-gray-500 md:hidden">Cambio sesión</span>
                          <span className={`font-mono ${r.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {formatPercent(r.changePercent, { fromRatio: false, digits: 2, signDisplay: 'always' })}
                          </span>
                        </td>
                        <td className="flex items-center justify-between gap-3 py-1 md:table-cell md:py-3 md:pr-4 md:text-right">
                          <span className="text-xs text-gray-500 md:hidden">Market Cap</span>
                          <span className="font-mono text-gray-300">
                            {formatCompact(r.marketCap, { maximumFractionDigits: 1 })}
                          </span>
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
                  <span className="shrink-0 font-semibold text-gray-100">{formatPrice(i.price, 'USD')}</span>
                </div>
              ))}
              {indices.length === 0 && <p className="text-sm text-gray-500">Sin datos de índices</p>}
            </div>
            <p className="mt-4 text-xs text-gray-500">S&amp;P 500, Nasdaq, Bitcoin, Oro, Plata — valores reales.</p>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}


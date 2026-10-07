import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import BackendOffline from '@/components/system/BackendOffline';
import { getInvestor } from '@/lib/actions/investors.actions';
import { isBackendUnavailableError } from '@/lib/backend-offline';
import { formatNumber, formatPercent, NA } from '@/lib/format';

import { InvestorVideos } from '../_components/InvestorVideos';
import { InvestorAvatar } from '../_components/Avatar';
import { INVESTOR_PHOTOS } from '../_components/photos';
import { PublicProfileSection } from '../_components/PublicProfile';
import { Pagination, paginate } from '../_components/Pagination';
import { periodLabel, usd } from '../_components/format';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type PageProps = {
    params: Promise<{ slug: string }>;
    searchParams: Promise<{ vista?: string; pagina?: string }>;
};

const VIEWS = [
    { id: 'posiciones', label: 'Posiciones' },
    { id: 'distribucion', label: 'Distribución' },
    { id: 'cambios', label: 'Cambios' },
] as const;

const CHANGE_LABELS: Record<string, string> = {
    new: 'Nueva',
    closed: 'Cerrada',
    increased: 'Aumentada',
    decreased: 'Reducida',
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
    const { slug } = await params;
    return { title: `Inversores · ${slug}` };
}

export default async function InvestorPage({ params, searchParams }: PageProps) {
    const { slug } = await params;
    const { vista, pagina } = await searchParams;
    const view = VIEWS.some((item) => item.id === vista) ? vista : 'posiciones';

    let investor: Awaited<ReturnType<typeof getInvestor>>;
    try {
        investor = await getInvestor(slug);
    } catch (error) {
        if (isBackendUnavailableError(error)) {
            return <BackendOffline feature="Inversores" retryHref={`/inversores/${slug}`} />;
        }
        throw error;
    }
    if (!investor) notFound();

    const positionsPage = paginate(investor.holdings, pagina, 25);
    const changeRows =
        investor.changes?.status === 'ok' ? investor.changes.changes.filter((row) => row.change !== 'unchanged') : [];
    const changesPage = paginate(changeRows, pagina, 25);

    const photo = INVESTOR_PHOTOS[investor.slug];
    const hasPortfolio = investor.has_13f && investor.holdings.length > 0;
    const source = `Fuente: SEC, Form 13F (EDGAR), informe a ${periodLabel(investor.report_date)}.`;

    return (
        <main id="content" tabIndex={-1} className="mx-auto flex w-full min-w-0 max-w-4xl flex-col gap-10 overflow-x-clip py-6">
            <Link className="text-sm text-gray-500 hover:text-gray-300" href="/inversores">
                Inversores
            </Link>

            <header className="flex items-center gap-5">
                <InvestorAvatar name={investor.name} size="lg" slug={investor.slug} />
                <div className="min-w-0">
                    <h1 className="truncate text-3xl font-semibold text-gray-100">{investor.name}</h1>
                    <p className="text-base text-gray-500">{investor.firm}</p>
                    {photo ? (
                        <p className="mt-1 text-xs text-gray-600">
                            Foto: {photo.author},{' '}
                            <a className="hover:underline" href={photo.licenseUrl} rel="noreferrer" target="_blank">
                                {photo.license}
                            </a>
                            , vía{' '}
                            <a className="hover:underline" href={photo.source} rel="noreferrer" target="_blank">
                                Wikimedia Commons
                            </a>
                        </p>
                    ) : null}
                </div>
            </header>

            {!investor.has_13f ? (
                investor.public_profile ? (
                    <PublicProfileSection profile={investor.public_profile} />
                ) : (
                    <p className="rounded-2xl border border-gray-800 bg-surface-1 p-6 text-base text-gray-400">
                        Sin datos: no presenta 13F.
                    </p>
                )
            ) : !hasPortfolio ? (
                <p className="rounded-2xl border border-gray-800 bg-surface-1 p-6 text-base text-gray-400">
                    Sin datos todavía: falta sincronizar su 13F.
                </p>
            ) : (
                <>
                    <div className="flex items-end justify-between gap-4">
                        <div>
                            <p className="text-3xl font-semibold text-gray-100">{usd(investor.value_usd_thousands, investor.report_date)}</p>
                            <p className="text-sm text-gray-500">
                                {investor.positions !== null
                                    ? `${formatNumber(investor.positions, { maximumFractionDigits: 0 })} posiciones`
                                    : NA}
                            </p>
                        </div>
                        <p className="text-sm text-gray-500">Cartera a {periodLabel(investor.report_date)}</p>
                    </div>

                    {investor.coverage === 'partial' ? (
                        <p
                            className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-200"
                            role="status"
                        >
                            Datos parciales: la sincronización no se completó o no cuadra con el total que declara el propio
                            13F. Las cifras pueden estar incompletas.
                        </p>
                    ) : null}

                    <nav aria-label="Vistas de la cartera" className="flex gap-6 border-b border-gray-800">
                        {VIEWS.map((item) => (
                            <Link
                                aria-current={item.id === view ? 'page' : undefined}
                                className={`-mb-px border-b-2 pb-3 text-sm ${
                                    item.id === view
                                        ? 'border-lime-300 text-gray-100'
                                        : 'border-transparent text-gray-500 hover:text-gray-300'
                                }`}
                                href={`/inversores/${investor.slug}?vista=${item.id}`}
                                key={item.id}
                            >
                                {item.label}
                            </Link>
                        ))}
                    </nav>

                    {view === 'posiciones' ? (
                        <ul className="flex flex-col divide-y divide-gray-900">
                            {positionsPage.items.map((row) => (
                                <li
                                    className="flex items-center justify-between gap-4 py-3"
                                    key={`${row.cusip}-${row.title_of_class}-${row.put_call ?? ''}`}
                                >
                                    <span className="min-w-0 truncate text-sm text-gray-200">
                                        {row.name_of_issuer}
                                        {row.put_call ? <span className="ml-2 text-xs text-gray-500">{row.put_call}</span> : null}
                                    </span>
                                    <span className="flex shrink-0 items-baseline gap-4 text-sm">
                                        <span className="text-gray-400">{usd(row.value_usd_thousands, investor.report_date)}</span>
                                        <span className="w-14 text-right text-gray-500">
                                            {row.weight_pct === null ? NA : formatPercent(row.weight_pct, { fromRatio: false })}
                                        </span>
                                    </span>
                                </li>
                            ))}
                        </ul>
                    ) : null}

                    {view === 'posiciones' ? (
                        <Pagination
                            basePath={`/inversores/${investor.slug}`}
                            page={positionsPage.page}
                            params={{ vista: 'posiciones' }}
                            total={positionsPage.total}
                        />
                    ) : null}

                    {view === 'distribucion' ? (
                        <ul className="flex flex-col gap-4">
                            {investor.holdings.slice(0, 10).map((row) => (
                                <li className="flex flex-col gap-2" key={`${row.cusip}-${row.title_of_class}-${row.put_call ?? ''}`}>
                                    <span className="flex items-baseline justify-between gap-4 text-sm">
                                        <span className="min-w-0 truncate text-gray-200">{row.name_of_issuer}</span>
                                        <span className="shrink-0 text-gray-500">
                                            {row.weight_pct === null ? NA : formatPercent(row.weight_pct, { fromRatio: false })}
                                        </span>
                                    </span>
                                    <span className="h-1.5 w-full overflow-hidden rounded-full bg-gray-900">
                                        <span
                                            className="block h-full rounded-full bg-lime-300/70"
                                            style={{ width: `${Math.min(100, Math.max(0, row.weight_pct ?? 0))}%` }}
                                        />
                                    </span>
                                </li>
                            ))}
                        </ul>
                    ) : null}

                    {view === 'cambios' ? (
                        investor.changes?.status === 'ok' ? (
                            <div className="flex flex-col gap-4">
                                <p className="text-sm text-gray-500">
                                    {periodLabel(investor.changes.previous_report)} a {periodLabel(investor.changes.latest_report)}
                                </p>
                                <ul className="flex flex-col divide-y divide-gray-900">
                                    {changesPage.items.map((row) => (
                                            <li
                                                className="flex items-center justify-between gap-4 py-3"
                                                key={`${row.cusip}-${row.title_of_class}-${row.put_call ?? ''}`}
                                            >
                                                <span className="min-w-0 truncate text-sm text-gray-200">{row.name_of_issuer}</span>
                                                <span className="shrink-0 text-sm text-gray-400">{CHANGE_LABELS[row.change] ?? row.change}</span>
                                            </li>
                                        ))}
                                </ul>
                                <Pagination
                                    basePath={`/inversores/${investor.slug}`}
                                    page={changesPage.page}
                                    params={{ vista: 'cambios' }}
                                    total={changesPage.total}
                                />
                            </div>
                        ) : (
                            <p className="text-sm text-gray-500">
                                Sin datos de cambios: hacen falta dos trimestres sincronizados para comparar.
                            </p>
                        )
                    ) : null}

                    <p className="text-xs text-gray-500">
                        {source} Trimestral, con hasta 45 días de retardo; solo posiciones largas en EE. UU. Tal como se
                        declaró, sin inferir tickers.
                    </p>
                </>
            )}
            <InvestorVideos videos={investor.videos} />
        </main>
    );
}

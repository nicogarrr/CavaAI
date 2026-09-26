import { Building2, ExternalLink, FileText } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import {
    getManagerChanges,
    getManagerHoldings,
    getOwnershipManagers,
    type ManagerChanges,
    type ManagerHoldings,
} from '@/lib/actions/ownership.actions';

import SyncButton from './SyncButton';

/** El backend publica las limitaciones del 13F como constante revisada en
 *  inglés; en UI van en español (F33). Texto desconocido: se muestra tal cual,
 *  nunca se oculta una limitación. */
const LIMITATION_LABELS: Record<string, string> = {
    'Quarterly cadence with up to a 45-day reporting lag':
        'Periodicidad trimestral con hasta 45 días de retardo en la declaración',
    'Long-only US-listed positions; no shorts, no non-13F securities':
        'Solo posiciones largas cotizadas en EE. UU.; sin cortos ni valores fuera del 13F',
    'Holdings as filed: CUSIP + issuer name; tickers never inferred':
        'Posiciones tal como se declararon: CUSIP y nombre del emisor; nunca se infieren tickers',
    'Amendments are separate immutable filings':
        'Las enmiendas son filings inmutables independientes',
};

const CHANGE_LABELS: Record<string, string> = {
    new: 'nueva posicion',
    closed: 'cerrada',
    increased: 'aumentada',
    decreased: 'reducida',
    unchanged: 'sin cambios',
};

export const dynamic = 'force-dynamic';
export const revalidate = 0;

function formatValueUsd(thousands: number | null): string {
    if (thousands === null) return 'n/d';
    const millions = thousands / 1000;
    return `$${millions.toLocaleString('es-ES', { maximumFractionDigits: 0 })}M`;
}

function formatShares(shares: number | null): string {
    if (shares === null) return 'n/d';
    return shares.toLocaleString('es-ES', { maximumFractionDigits: 0 });
}

type PageProps = {
    searchParams: Promise<{ cik?: string }>;
};

export default async function OwnershipPage({ searchParams }: PageProps) {
    const { cik: selectedCik } = await searchParams;
    const managersResult = await getOwnershipManagers().catch(() => null);
    const managers = managersResult?.managers ?? [];
    const limitations = managersResult?.limitations ?? [];
    const activeCik = selectedCik ?? managers[0]?.cik ?? null;
    const holdings: ManagerHoldings | null = activeCik
        ? await getManagerHoldings(activeCik).catch(() => null)
        : null;
    const changes: ManagerChanges | null = activeCik
        ? await getManagerChanges(activeCik).catch(() => null)
        : null;

    return (
        <main id="content" tabIndex={-1} className="mx-auto flex w-full min-w-0 max-w-6xl flex-col gap-6 overflow-x-clip">
            <header className="flex flex-col gap-3 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
                <div>
                    <p className="text-sm font-semibold uppercase text-teal-300">Ownership</p>
                    <h1 className="mt-1 text-3xl font-bold text-gray-100">Propiedad institucional (13F)</h1>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-400">
                        Carteras de gestores institucionales revisados, tal como se declaran ante la SEC
                        (Form 13F, EDGAR; fuente oficial y gratuita). Datos tal y como se presentaron:
                        CUSIP y nombre del emisor, sin inferir tickers. Las enmiendas (13F-HR/A) son
                        filings inmutables independientes.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <div className="flex items-center gap-2 rounded-lg border border-gray-800 bg-[#111111] px-3 py-2 text-sm text-gray-300">
                        <Building2 className="h-4 w-4 text-teal-300" />
                        SEC 13F
                    </div>
                    <SyncButton />
                </div>
            </header>

            {limitations.length ? (
                <section className="rounded-xl border border-amber-900/60 bg-amber-950/20 p-4">
                    <h2 className="text-sm font-semibold text-amber-200">Limites de este dato</h2>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-gray-400">
                        {limitations.map((item) => <li key={item}>{LIMITATION_LABELS[item] ?? item}</li>)}
                    </ul>
                </section>
            ) : null}

            {!managers.length ? (
                <section className="rounded-xl border border-gray-800 bg-[#101010] p-5 text-sm text-gray-400">
                    No hay gestores revisados disponibles (o el backend no responde). La lista de
                    gestores es una tabla revisada en codigo; se amplia explicitamente.
                </section>
            ) : (
                <section className="flex flex-wrap gap-2">
                    {managers.map((manager) => (
                        <a
                            className={`rounded-lg border px-3 py-2 text-sm ${manager.cik === activeCik ? 'border-teal-700 bg-teal-950/30 text-teal-200' : 'border-gray-800 bg-[#101010] text-gray-300 hover:border-gray-700'}`}
                            href={`/ownership?cik=${manager.cik}`}
                            key={manager.cik}
                        >
                            {manager.name}
                            <span className="ml-2 text-xs text-gray-500">CIK {manager.cik}</span>
                        </a>
                    ))}
                </section>
            )}

            {activeCik && holdings ? (
                holdings.status === 'ok' ? (
                    <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
                        <div className="flex flex-col gap-2 md:flex-row md:items-center">
                            <h2 className="font-semibold text-gray-100">
                                {holdings.manager} - informe {holdings.report_date}
                            </h2>
                            <Badge className="md:ml-auto" variant="outline">
                                cobertura {holdings.coverage}
                            </Badge>
                        </div>
                        <div className="mt-4 overflow-x-auto">
                            <table className="w-full min-w-[820px] text-left text-sm">
                                <thead className="text-xs uppercase text-gray-500">
                                    <tr>
                                        <th className="border-b border-gray-800 py-2">Emisor (tal como se declaro)</th>
                                        <th className="border-b border-gray-800 py-2">Clase</th>
                                        <th className="border-b border-gray-800 py-2">CUSIP</th>
                                        <th className="border-b border-gray-800 py-2 text-right">Valor</th>
                                        <th className="border-b border-gray-800 py-2 text-right">Acciones</th>
                                        <th className="border-b border-gray-800 py-2">Tipo</th>
                                        <th className="border-b border-gray-800 py-2">Filing</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {holdings.holdings.map((row) => (
                                        <tr className="border-b border-gray-900" key={`${row.accession_number}-${row.cusip}-${row.title_of_class}-${row.put_call ?? ''}`}>
                                            <td className="py-3 text-gray-200">
                                                {row.name_of_issuer}
                                                {row.is_amendment ? (
                                                    <Badge className="ml-2" variant="outline">enmienda</Badge>
                                                ) : null}
                                            </td>
                                            <td className="py-3 text-gray-400">{row.title_of_class || '-'}</td>
                                            <td className="py-3 font-mono text-xs text-gray-400">{row.cusip}</td>
                                            <td className="py-3 text-right text-gray-200">{formatValueUsd(row.value_usd_thousands)}</td>
                                            <td className="py-3 text-right text-gray-400">{formatShares(row.shares)}</td>
                                            <td className="py-3 text-gray-400">{row.put_call ?? row.share_type}</td>
                                            <td className="py-3">
                                                <a
                                                    className="inline-flex items-center gap-1 text-teal-300 hover:text-teal-200"
                                                    href={row.filing_url}
                                                    rel="noreferrer"
                                                    target="_blank"
                                                >
                                                    <FileText className="h-3.5 w-3.5" />
                                                    XML
                                                    <ExternalLink className="h-3 w-3" />
                                                </a>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        {holdings.provenance ? (
                            <p className="mt-3 text-xs text-gray-500">
                                Fuente: {holdings.provenance.source} ({holdings.provenance.source_kind}),
                                obtenido {new Date(holdings.provenance.fetched_at).toLocaleString('es-ES')}.
                            </p>
                        ) : null}
                    </section>
                ) : (
                    <section className="rounded-xl border border-gray-800 bg-[#101010] p-5 text-sm text-gray-400">
                        <h2 className="font-semibold text-gray-100">Sin datos 13F todavia</h2>
                        <p className="mt-2">
                            Este gestor aun no se ha sincronizado. Pulsa &quot;Sincronizar 13F&quot; para
                            descargar su ultimo informe desde SEC EDGAR (gratuito, fuente oficial).
                        </p>
                    </section>
                )
            ) : null}
            {activeCik && changes ? (
                changes.status === 'ok' ? (
                    <section className="rounded-xl border border-gray-800 bg-[#101010] p-5">
                        <div className="flex flex-col gap-2 md:flex-row md:items-center">
                            <h2 className="font-semibold text-gray-100">
                                Cambios trimestre a trimestre ({changes.previous_report} → {changes.latest_report})
                            </h2>
                            <Badge className="md:ml-auto" variant="outline">
                                {changes.changes.filter((c) => c.change !== 'unchanged').length} movimientos
                            </Badge>
                        </div>
                        <p className="mt-2 text-xs text-gray-500">{changes.compared_accessions?.rule}</p>
                        <div className="mt-4 overflow-x-auto">
                            <table className="w-full min-w-[720px] text-left text-sm">
                                <thead className="text-xs uppercase text-gray-500">
                                    <tr>
                                        <th className="border-b border-gray-800 py-2">Emisor</th>
                                        <th className="border-b border-gray-800 py-2">CUSIP</th>
                                        <th className="border-b border-gray-800 py-2">Cambio</th>
                                        <th className="border-b border-gray-800 py-2 text-right">Acciones antes</th>
                                        <th className="border-b border-gray-800 py-2 text-right">Acciones ahora</th>
                                        <th className="border-b border-gray-800 py-2 text-right">Valor antes</th>
                                        <th className="border-b border-gray-800 py-2 text-right">Valor ahora</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {changes.changes.filter((row) => row.change !== 'unchanged').map((row) => (
                                        <tr className="border-b border-gray-900" key={`${row.cusip}-${row.title_of_class}-${row.put_call ?? ''}`}>
                                            <td className="py-3 text-gray-200">{row.name_of_issuer}</td>
                                            <td className="py-3 font-mono text-xs text-gray-400">{row.cusip}</td>
                                            <td className="py-3">
                                                <Badge variant="outline">{CHANGE_LABELS[row.change]}</Badge>
                                            </td>
                                            <td className="py-3 text-right text-gray-400">{formatShares(row.shares_previous)}</td>
                                            <td className="py-3 text-right text-gray-200">{formatShares(row.shares_latest)}</td>
                                            <td className="py-3 text-right text-gray-400">{formatValueUsd(row.value_usd_thousands_previous)}</td>
                                            <td className="py-3 text-right text-gray-200">{formatValueUsd(row.value_usd_thousands_latest)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        {changes.changes.every((c) => c.change === 'unchanged') ? (
                            <p className="mt-3 text-sm text-gray-400">Sin movimientos entre los dos ultimos informes.</p>
                        ) : null}
                    </section>
                ) : (
                    <section className="rounded-xl border border-gray-800 bg-[#101010] p-5 text-sm text-gray-400">
                        <h2 className="font-semibold text-gray-100">Cambios QoQ no disponibles todavia</h2>
                        <p className="mt-2">
                            {changes.status === 'insufficient_history'
                                ? 'Hacen falta dos informes 13F almacenados para comparar; estara disponible tras el proximo trimestre.'
                                : 'Sincroniza este gestor para poder comparar informes.'}
                        </p>
                    </section>
                )
            ) : null}
        </main>
    );
}

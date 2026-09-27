'use client';

import { formatDate, formatUserDateTime, formatMoney, formatNumber } from '@/lib/format';
import { t } from '@/lib/i18n/t';
import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ExternalLink, Search, Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { formatRecordValue, type DataRecord } from '@/components/data/RecordViews';
import type { InsiderFilingsResult, InsiderSignalsResult } from '@/lib/actions/insider.actions';
import { getInsiderSignals } from '@/lib/actions/insider.actions';
import { analyzedCountCopy, degradedCopy } from '@/lib/insider-status-copy';
import { toast } from 'sonner';

interface InsiderSignalsViewProps {
    initialTicker: string;
    initialResult: InsiderSignalsResult | null;
    /** Filings Form 4/4-A persistidos (GET /api/insider/filings). */
    initialFilings?: InsiderFilingsResult | null;
}

function signalTone(signal: unknown): 'default' | 'outline' {
    return signal === 'cluster_buy' || signal === 'c_suite_buy' || signal === 'big_buy'
        ? 'default'
        : 'outline';
}

function moneyText(value: unknown): string {
    if (typeof value !== 'number' || !Number.isFinite(value)) return formatRecordValue(value);
    return formatMoney(value, 'USD', { maximumFractionDigits: 0 });
}

function formBadge(form: unknown): { label: string; amended: boolean } | null {
    if (typeof form !== 'string' || !form) return null;
    if (form.endsWith('/A')) return { label: 'Enmienda ' + form, amended: true };
    return { label: 'Form ' + form, amended: false };
}

function secLink(sourceUrl: unknown): string | null {
    return typeof sourceUrl === 'string' && sourceUrl.startsWith('https://') ? sourceUrl : null;
}

function formatFetchedAt(value: unknown): string {
    if (typeof value !== 'string' || !value) return t('signals.noDate');
    return formatUserDateTime(value);
}

/** Fechas de Form 4: son días del calendario EDGAR (US), no instantes. Se
 *  formatean sin timeZone para que el día salga siempre igual (parseo local +
 *  formato local es invariante de zona). */
function filingDateText(value: unknown): string {
    return typeof value === 'string' && value ? formatDate(value) : formatRecordValue(value);
}

/** Contadores del backend: enteros con separadores es-ES. */
function countText(value: unknown): string {
    return typeof value === 'number' ? formatNumber(value, { maximumFractionDigits: 0 }) : formatRecordValue(value);
}

export default function InsiderSignalsView({ initialTicker, initialResult, initialFilings }: InsiderSignalsViewProps) {
    const router = useRouter();
    const [ticker, setTicker] = useState(initialTicker);
    const [notifying, setNotifying] = useState(false);

    const handleSearch = (event: React.FormEvent) => {
        event.preventDefault();
        const clean = ticker.trim().toUpperCase();
        if (!clean) return;
        router.push(`/insider?ticker=${encodeURIComponent(clean)}`);
    };

    /** Evaluacion inmediata con notify=true (enganche Telegram best-effort, una sola vez). */
    const handleEvaluateNotify = async () => {
        if (!initialTicker) return;
        setNotifying(true);
        try {
            const result = await getInsiderSignals(initialTicker, { notify: true });
            const notification = result.notification as { status?: string } | undefined;
            toast.success(
                notification?.status === 'delivered'
                    ? `Aviso insider enviado para ${initialTicker}`
                    : `Evaluado ${initialTicker}: sin aviso Telegram (${notification?.status ?? 'omitido'})`,
            );
        } catch {
            toast.error(`No se pudo evaluar el aviso para ${initialTicker}`);
        } finally {
            setNotifying(false);
        }
    };

    const signals: DataRecord[] = Array.isArray(initialResult?.signals)
        ? (initialResult.signals as DataRecord[])
        : [];

    return (
        <div className="grid w-full min-w-0 grid-cols-1 gap-6">
            <Card className="rounded-lg border border-gray-700 bg-gray-800/50">
                <CardHeader className="border-b border-gray-700/50 pb-4">
                    <div className="flex items-center gap-3">
                        <Users aria-hidden="true" className="h-5 w-5 text-teal-400" />
                        <div>
                            <CardTitle className="text-lg font-semibold text-gray-100">
                                Buscar señales por ticker
                            </CardTitle>
                            <CardDescription className="mt-0.5 text-sm text-gray-500">
                                Compras insider (Form 4, código P — mercado abierto o privado): cluster, C-suite y grandes compras
                            </CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="pt-4">
                    <form onSubmit={handleSearch} className="flex w-full max-w-md flex-col gap-3 sm:flex-row">
                        <Input
                            value={ticker}
                            onChange={(event) => setTicker(event.target.value.toUpperCase())}
                            placeholder={t('insider.searchPlaceholder')}
                            maxLength={20}
                            className="h-11 w-full bg-gray-900 font-mono uppercase"
                        />
                        <Button type="submit" className="h-11 w-full gap-2 bg-teal-600 hover:bg-teal-700 sm:w-auto">
                            <Search aria-hidden="true" className="h-4 w-4" />
                            Buscar
                        </Button>
                    </form>
                </CardContent>
            </Card>

            {/* Estado del monitor + filings persistidos (GET /api/insider/filings) */}
            {initialTicker ? (
                <div className="flex flex-wrap items-center gap-2">
                    {(!initialResult || !initialFilings) ? (
                        <span className="text-xs text-amber-300">
                            Lectura parcial: una de las fuentes no respondió. Reintenta la búsqueda.
                        </span>
                    ) : null}
                    <Badge
                        variant={initialFilings && initialFilings.status === 'ok' ? 'default' : 'outline'}
                    >
                        Monitor cada 15 min · {countText(initialFilings?.count ?? 0)} filings persistidos
                    </Badge>
                    {initialFilings && initialFilings.status !== 'ok' ? (
                        <span className="text-xs text-amber-300">
                            lectura durable no disponible ({formatRecordValue(initialFilings.reason ?? initialFilings.status)})
                        </span>
                    ) : null}
                    {/* El efecto real es una evaluacion inmediata de una sola
                        vez (evalua y, si hay senal, envia Telegram ahora): no
                        suscribe nada. Un checkbox sugeriria una preferencia
                        persistente que no existe (F173). */}
                    <Button
                        className="ml-auto min-h-[44px] text-xs sm:min-h-0"
                        disabled={notifying || !initialResult}
                        onClick={() => handleEvaluateNotify()}
                        size="sm"
                        variant="outline"
                    >
                        {notifying ? 'Evaluando aviso…' : 'Evaluar aviso Telegram ahora'}
                    </Button>
                </div>
            ) : null}

            {!initialTicker ? (
                <p className="rounded-lg border border-dashed border-gray-800 p-6 text-sm text-gray-500">
                    Introduce un ticker para ver sus señales insider.
                </p>
            ) : !initialResult ? (
                <p className="rounded-lg border border-red-900/50 bg-red-950/20 p-6 text-sm text-red-200">
                    No se pudieron cargar las señales de {initialTicker}. Reintenta más tarde.
                </p>
            ) : initialResult.status === 'unavailable' ? (
                <div className="rounded-lg border border-amber-900/60 bg-amber-950/20 p-6 text-sm text-amber-200">
                    {/* unavailable solo se devuelve cuando el ticker no resuelve CIK en EDGAR:
                        eso prueba «no es emisor SEC US», nada mas. La reason estable
                        («not a US SEC filer») ya la dice la cabecera; otra reason seria detalle. */}
                    <p>
                        {initialTicker}: no es un emisor SEC estadounidense (sin CIK en EDGAR), así
                        que no tiene señales insider Form 4.
                    </p>
                    {typeof initialResult.reason === 'string' &&
                    initialResult.reason &&
                    initialResult.reason !== 'not a US SEC filer' ? (
                        <p className="mt-2 text-xs text-amber-300/80">
                            Detalle técnico: {formatRecordValue(initialResult.reason)}
                        </p>
                    ) : null}
                </div>
            ) : initialResult.status === 'degraded' ? (
                // F234: «AAPL: degraded» a pelo no decía nada. El backend ya
                // devuelve cuántos Form 4 se escanearon y cuántos fallaron:
                // un estado técnico se explica con sus números, nunca con la
                // palabra cruda. Y se deja claro que no es un «sin actividad».
                <div className="rounded-lg border border-amber-900/60 bg-amber-950/20 p-6 text-sm text-amber-200">
                    <p>
                        {degradedCopy(initialTicker, initialResult, countText).header} Es un fallo
                        de lectura, no una ausencia de actividad insider. Reintenta más tarde.
                    </p>
                    {degradedCopy(initialTicker, initialResult, countText).detail ? (
                        <p className="mt-2 text-xs text-amber-300/80">
                            Detalle técnico: {degradedCopy(initialTicker, initialResult, countText).detail}
                        </p>
                    ) : null}
                </div>
            ) : (
                // ok y partial: las señales parseadas son reales; partial las
                // muestra con su aviso de cobertura incompleta.
                <>
                    {initialResult.status === 'partial' ? (
                        <p className="rounded-lg border border-amber-900/60 bg-amber-950/20 p-6 text-sm text-amber-200">
                            {initialTicker}: lectura incompleta — {countText(initialResult.filings_parsed)} de{' '}
                            {countText(initialResult.filings_scanned)} Form 4 leídos (
                            {countText(initialResult.filings_failed)} con error). Las señales de abajo
                            cubren solo los filings legibles.
                        </p>
                    ) : null}
                    {signals.length === 0 ? (
                        <p className="rounded-lg border border-dashed border-gray-800 p-6 text-sm text-gray-500">
                            {initialTicker}: {t('insider.noSignals')}(
                            {analyzedCountCopy(initialResult.status, initialResult, countText)}).
                        </p>
                    ) : (
                <Card className="rounded-lg border border-gray-700 bg-gray-800/50">
                    <CardHeader className="flex flex-col gap-3 space-y-0 border-b border-gray-700/50 pb-4 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex items-center gap-3">
                            <Users aria-hidden="true" className="h-5 w-5 text-teal-400" />
                            <div>
                                <CardTitle className="text-lg font-semibold text-gray-100">
                                    Señales ·{' '}
                                    <Link
                                        href={`/research/${encodeURIComponent(initialTicker)}`}
                                        className="font-mono text-teal-300 hover:text-teal-200 hover:underline"
                                    >
                                        {initialTicker}
                                    </Link>
                                </CardTitle>
                                <CardDescription className="mt-0.5 text-sm text-gray-500">
                                    {formatNumber(signals.length, { maximumFractionDigits: 0 })} señales ·{' '}
                                    {countText(initialResult.buy_count)} compras ·{' '}
                                    {countText(initialResult.filings_scanned)} filings · datos al{' '}
                                    {t('signals.asOf', { date: formatFetchedAt((initialResult.provenance as Record<string, unknown> | undefined)?.fetched_at ?? initialResult.fetched_at) })}
                                </CardDescription>
                            </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                            <Badge>cluster</Badge>
                            <Badge variant="outline">C-suite</Badge>
                        </div>
                    </CardHeader>
                    <CardContent className="min-w-0 pt-4">
                        <div className="hidden md:block">
                        <Table regionLabel="Señales insider del ticker">
                            <TableCaption className="sr-only">Compras insider registradas: tipo de señal, persona, fecha, importe y detalle con enlace al filing de la SEC.</TableCaption>
                            <TableHeader>
                                <TableRow className="border-gray-700 hover:bg-transparent">
                                    <TableHead className="text-xs font-semibold uppercase text-gray-500">{t('insider.signal')}</TableHead>
                                    <TableHead className="text-xs font-semibold uppercase text-gray-500">{t('insider.insider')}</TableHead>
                                    <TableHead className="text-xs font-semibold uppercase text-gray-500">{t('insider.date')}</TableHead>
                                    <TableHead className="text-right text-xs font-semibold uppercase text-gray-500">{t('insider.value')}</TableHead>
                                    <TableHead className="text-xs font-semibold uppercase text-gray-500">{t('insider.detail')}</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {signals.map((signal, index) => (
                                    <TableRow key={index} className="border-gray-700/50">
                                        <TableCell>
                                            <Badge variant={signalTone(signal.signal)}>
                                                {formatRecordValue(signal.signal)}
                                            </Badge>
                                        </TableCell>
                                        <TableCell className="text-sm text-gray-200">
                                            {formatRecordValue(signal.insider)}
                                            {signal.officer_title ?? signal.role ? (
                                                <span className="block text-xs text-gray-500">
                                                    {formatRecordValue(signal.officer_title ?? signal.role)}
                                                </span>
                                            ) : null}
                                        </TableCell>
                                        <TableCell className="text-sm text-gray-300">
                                            {filingDateText(signal.date ?? signal.window_start)}
                                        </TableCell>
                                        <TableCell className="text-right text-sm font-semibold text-gray-100">
                                            {moneyText(signal.value ?? signal.total_value)}
                                        </TableCell>
                                        <TableCell className="max-w-md text-sm text-gray-400">
                                            <span className="line-clamp-3">{formatRecordValue(signal.detail)}</span>
                                            <span className="mt-1 flex flex-wrap items-center gap-2">
                                                {formBadge(signal.form) ? (
                                                    <Badge variant="outline">{formBadge(signal.form)!.label}</Badge>
                                                ) : null}
                                                {signal.multi_reporter === true ? (
                                                    <span className="text-xs text-gray-500">filing conjunto</span>
                                                ) : null}
                                                {secLink(signal.source_url) ? (
                                                    <a
                                                        href={secLink(signal.source_url)!}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="inline-flex items-center gap-1 text-xs text-teal-300 hover:text-teal-200 hover:underline"
                                                    >
                                                        Ver filing SEC <ExternalLink aria-hidden="true" className="h-3 w-3" />
                                                    </a>
                                                ) : null}
                                            </span>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                        </div>
                        <div className="grid grid-cols-1 gap-3 md:hidden">
                            {signals.map((signal, index) => (
                                <article className="min-w-0 rounded-lg border border-gray-700/50 bg-gray-900/50 p-4 break-words" key={index}>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <Badge variant={signalTone(signal.signal)}>{formatRecordValue(signal.signal)}</Badge>
                                        <span className="ml-auto text-sm font-semibold text-gray-100">{moneyText(signal.value ?? signal.total_value)}</span>
                                    </div>
                                    <div className="mt-3 text-sm font-medium text-gray-200">{formatRecordValue(signal.insider)}</div>
                                    {signal.officer_title ?? signal.role ? (
                                        <div className="text-xs text-gray-500">{formatRecordValue(signal.officer_title ?? signal.role)}</div>
                                    ) : null}
                                    <div className="mt-1 text-xs text-gray-500">{filingDateText(signal.date ?? signal.window_start)}</div>
                                    <div className="mt-2 text-sm leading-6 text-gray-400"><span className="line-clamp-3">{formatRecordValue(signal.detail)}</span></div>
                                    <div className="mt-2 flex flex-wrap items-center gap-2">
                                        {formBadge(signal.form) ? <Badge variant="outline">{formBadge(signal.form)!.label}</Badge> : null}
                                        {signal.multi_reporter === true ? <span className="text-xs text-gray-500">filing conjunto</span> : null}
                                        {secLink(signal.source_url) ? (
                                            <a
                                                href={secLink(signal.source_url)!}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="inline-flex items-center gap-1 text-xs text-teal-300 hover:text-teal-200 hover:underline"
                                            >
                                                Ver filing SEC <ExternalLink aria-hidden="true" className="h-3 w-3" />
                                            </a>
                                        ) : null}
                                    </div>
                                </article>
                            ))}
                        </div>
                    </CardContent>
                </Card>
                    )}
                </>
            )}
            {initialTicker && initialFilings && initialFilings.status === 'ok' && initialFilings.filings.length > 0 ? (
                <Card className="rounded-lg border border-gray-700 bg-gray-800/50">
                    <CardHeader className="border-b border-gray-700/50 pb-4">
                        <CardTitle className="text-lg font-semibold text-gray-100">
                            Filings persistidos · {initialFilings.count}
                        </CardTitle>
                        <CardDescription className="mt-0.5 text-sm text-gray-500">
                            Lectura durable (Form 4/4-A inmutables; las enmiendas son filas propias)
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <ul className="space-y-2">
                            {initialFilings.filings.slice(0, 10).map((filing) => (
                                <li
                                    key={filing.accession_number}
                                    className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm"
                                >
                                    <Badge variant="outline">{filing.form}</Badge>
                                    {filing.is_amendment ? <Badge>Enmienda</Badge> : null}
                                    <span className="font-mono text-gray-300">
                                        {filingDateText(filing.filing_date)}
                                    </span>
                                    <span className="text-gray-500">
                                        {formatNumber(filing.transaction_count, { maximumFractionDigits: 0 })} operaciones
                                    </span>
                                    {secLink(filing.source_url) ? (
                                        <a
                                            href={secLink(filing.source_url)!}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="inline-flex items-center gap-1 text-xs text-teal-300 hover:text-teal-200 hover:underline"
                                        >
                                            Ver filing SEC <ExternalLink aria-hidden="true" className="h-3 w-3" />
                                        </a>
                                    ) : null}
                                </li>
                            ))}
                        </ul>
                    </CardContent>
                </Card>
            ) : null}
        </div>
    );
}

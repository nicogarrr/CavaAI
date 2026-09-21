'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Search, Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { formatRecordValue, type DataRecord } from '@/components/data/RecordViews';
import type { InsiderSignalsResult } from '@/lib/actions/insider.actions';

interface InsiderSignalsViewProps {
    initialTicker: string;
    initialResult: InsiderSignalsResult | null;
}

function signalTone(signal: unknown): 'default' | 'outline' {
    return signal === 'cluster_buy' || signal === 'c_suite_buy' || signal === 'big_buy'
        ? 'default'
        : 'outline';
}

function moneyText(value: unknown): string {
    if (typeof value !== 'number' || !Number.isFinite(value)) return formatRecordValue(value);
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        maximumFractionDigits: 0,
    }).format(value);
}

export default function InsiderSignalsView({ initialTicker, initialResult }: InsiderSignalsViewProps) {
    const router = useRouter();
    const [ticker, setTicker] = useState(initialTicker);

    const handleSearch = (event: React.FormEvent) => {
        event.preventDefault();
        const clean = ticker.trim().toUpperCase();
        if (!clean) return;
        router.push(`/insider?ticker=${encodeURIComponent(clean)}`);
    };

    const signals: DataRecord[] = Array.isArray(initialResult?.signals)
        ? (initialResult.signals as DataRecord[])
        : [];

    return (
        <div className="grid gap-6">
            <Card className="rounded-lg border border-gray-700 bg-gray-800/50">
                <CardHeader className="border-b border-gray-700/50 pb-4">
                    <div className="flex items-center gap-3">
                        <Users className="h-5 w-5 text-teal-400" />
                        <div>
                            <CardTitle className="text-lg font-semibold text-gray-100">
                                Buscar señales por ticker
                            </CardTitle>
                            <CardDescription className="mt-0.5 text-sm text-gray-500">
                                Compras open-market (Form 4): cluster, C-suite y grandes compras
                            </CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="pt-4">
                    <form onSubmit={handleSearch} className="flex max-w-md gap-3">
                        <Input
                            value={ticker}
                            onChange={(event) => setTicker(event.target.value.toUpperCase())}
                            placeholder="AAPL"
                            maxLength={20}
                            className="bg-gray-900 font-mono uppercase"
                        />
                        <Button type="submit" className="gap-2 bg-teal-600 hover:bg-teal-700">
                            <Search className="h-4 w-4" />
                            Buscar
                        </Button>
                    </form>
                </CardContent>
            </Card>

            {!initialTicker ? (
                <p className="rounded-lg border border-dashed border-gray-800 p-6 text-sm text-gray-500">
                    Introduce un ticker para ver sus señales insider.
                </p>
            ) : !initialResult ? (
                <p className="rounded-lg border border-red-900/50 bg-red-950/20 p-6 text-sm text-red-200">
                    No se pudieron cargar las señales de {initialTicker}. Reintenta más tarde.
                </p>
            ) : initialResult.status !== 'ok' ? (
                <p className="rounded-lg border border-amber-900/60 bg-amber-950/20 p-6 text-sm text-amber-200">
                    {initialTicker}: {formatRecordValue(initialResult.reason ?? initialResult.status)}
                    {initialResult.status === 'unavailable'
                        ? ' — no es un emisor SEC estadounidense.' : ''}
                </p>
            ) : signals.length === 0 ? (
                <p className="rounded-lg border border-dashed border-gray-800 p-6 text-sm text-gray-500">
                    {initialTicker}: sin señales de compra insider en los últimos filings
                    ({formatRecordValue(initialResult.filings_scanned)} analizados).
                </p>
            ) : (
                <Card className="rounded-lg border border-gray-700 bg-gray-800/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-gray-700/50 pb-4">
                        <div className="flex items-center gap-3">
                            <Users className="h-5 w-5 text-teal-400" />
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
                                    {signals.length} señales · {formatRecordValue(initialResult.buy_count)} compras ·{' '}
                                    {formatRecordValue(initialResult.filings_scanned)} filings
                                </CardDescription>
                            </div>
                        </div>
                        <div className="flex gap-2">
                            <Badge>cluster</Badge>
                            <Badge variant="outline">C-suite</Badge>
                        </div>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <Table>
                            <TableHeader>
                                <TableRow className="border-gray-700 hover:bg-transparent">
                                    <TableHead className="text-xs font-semibold uppercase text-gray-500">Señal</TableHead>
                                    <TableHead className="text-xs font-semibold uppercase text-gray-500">Insider</TableHead>
                                    <TableHead className="text-xs font-semibold uppercase text-gray-500">Fecha</TableHead>
                                    <TableHead className="text-right text-xs font-semibold uppercase text-gray-500">Valor</TableHead>
                                    <TableHead className="text-xs font-semibold uppercase text-gray-500">Detalle</TableHead>
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
                                            {formatRecordValue(signal.date ?? signal.window_start)}
                                        </TableCell>
                                        <TableCell className="text-right text-sm font-semibold text-gray-100">
                                            {moneyText(signal.value ?? signal.total_value)}
                                        </TableCell>
                                        <TableCell className="max-w-md text-sm text-gray-400">
                                            <span className="line-clamp-3">{formatRecordValue(signal.detail)}</span>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}

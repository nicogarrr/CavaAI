'use client';

import { useMemo, useRef, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ArrowDownToLine, ArrowRightLeft, Upload } from 'lucide-react';
import type { ProPick } from '@/lib/actions/proPicks.actions';
import { formatNumber } from '@/lib/format';
import {
    buildMonthlySnapshot,
    diffSnapshots,
    isMonthlySnapshot,
    monthKey,
    monthLabelEs,
    type MonthlySnapshot,
    type RebalanceMove,
} from './monthlyRebalance';

interface MonthlyRebalanceViewProps {
    currentPicks: ProPick[];
    strategyId?: string;
    strategyName?: string;
    month?: string;
}

function MoveList({ moves, tone }: { moves: RebalanceMove[]; tone: 'in' | 'out' }) {
    if (moves.length === 0) {
        return <p className="text-sm text-gray-500">Ningún valor en este grupo.</p>;
    }
    return (
        <ul className="space-y-3">
            {moves.map((move) => (
                <li
                    key={move.symbol}
                    className={`rounded-lg border p-3 sm:p-4 ${
                        tone === 'in'
                            ? 'border-green-700/50 bg-green-950/20'
                            : 'border-red-700/50 bg-red-950/20'
                    }`}
                >
                    <div className="flex flex-wrap items-center gap-2">
                        <span className="text-base font-bold text-gray-100">{move.symbol}</span>
                        <Badge
                            variant="outline"
                            className={
                                tone === 'in'
                                    ? 'border-green-500/50 text-green-300'
                                    : 'border-red-500/50 text-red-300'
                            }
                        >
                            {tone === 'in' ? 'Entra' : 'Sale'}
                        </Badge>
                    </div>
                    <p className="mt-1 text-xs text-gray-500">{move.company}</p>
                    <p className="mt-2 text-sm leading-6 text-gray-300">{move.reason.text}</p>
                    {move.reason.metric !== undefined && move.reason.value !== undefined && (
                        <p className="mt-1 text-[11px] text-gray-500" title="Dato verificado">
                            Fuente: {move.reason.metric} = {String(move.reason.value)}
                        </p>
                    )}
                </li>
            ))}
        </ul>
    );
}

/**
 * Vista de rebalanceo mensual: diff entra/sale respecto al mes anterior con
 * motivo trazable por valor, y descarga del snapshot JSON mensual.
 *
 * El mes anterior sale del snapshot que se cargue (botón «Cargar snapshot
 * anterior»): sin snapshot previo se dice honestamente y no se inventa ningún
 * mes anterior.
 */
export default function MonthlyRebalanceView({
    currentPicks,
    strategyId = 'adaptive',
    strategyName = 'Selección Adaptativa IA',
    month = monthKey(),
}: MonthlyRebalanceViewProps) {
    const [previous, setPrevious] = useState<MonthlySnapshot | null>(null);
    const [fileError, setFileError] = useState<string | null>(null);
    const fileRef = useRef<HTMLInputElement>(null);

    const diff = useMemo(() => diffSnapshots(currentPicks, previous), [currentPicks, previous]);

    const handleFile = async (file: File | undefined) => {
        setFileError(null);
        if (!file) return;
        try {
            const parsed: unknown = JSON.parse(await file.text());
            if (!isMonthlySnapshot(parsed)) {
                setFileError('Ese archivo no es un snapshot mensual de CavaAI Propicks.');
                return;
            }
            setPrevious(parsed);
        } catch {
            setFileError('No se pudo leer el archivo JSON.');
        }
    };

    const downloadSnapshot = () => {
        const snapshot = buildMonthlySnapshot(currentPicks, strategyId, month);
        const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `propicks-${strategyId}-${snapshot.month}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    };

    return (
        <div className="space-y-4">
            <Card className="flex min-w-0 flex-col gap-4 rounded-lg border border-gray-700 bg-gray-800/50 p-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                        <ArrowRightLeft className="h-5 w-5 text-teal-400" />
                        <h3 className="text-base font-semibold text-gray-100">
                            Rebalanceo de {monthLabelEs(month)}
                        </h3>
                    </div>
                    <p className="mt-1 text-sm text-gray-400">
                        {strategyName} · {formatNumber(currentPicks.length, { maximumFractionDigits: 0 })} valores vigentes ·{' '}
                        {diff.hasPrevious && previous
                            ? `comparado con ${monthLabelEs(previous.month)}`
                            : 'aún sin snapshot del mes anterior'}
                    </p>
                </div>
                <div className="flex flex-col gap-2 sm:flex-row">
                    <input
                        ref={fileRef}
                        type="file"
                        accept="application/json"
                        className="hidden"
                        onChange={(e) => void handleFile(e.target.files?.[0])}
                    />
                    <Button
                        variant="outline"
                        onClick={() => fileRef.current?.click()}
                        className="h-11 gap-2"
                    >
                        <Upload className="h-4 w-4" />
                        Cargar snapshot anterior
                    </Button>
                    <Button onClick={downloadSnapshot} className="h-11 gap-2 bg-teal-600 hover:bg-teal-700">
                        <ArrowDownToLine className="h-4 w-4" />
                        Descargar snapshot JSON
                    </Button>
                </div>
            </Card>

            {fileError && (
                <Card className="rounded-lg border border-red-700 bg-red-900/20 p-4 text-center">
                    <p className="text-sm text-red-400">{fileError}</p>
                </Card>
            )}

            {!diff.hasPrevious && (
                <Card className="rounded-lg border border-amber-700/60 bg-amber-950/20 p-4">
                    <p className="text-sm leading-6 text-amber-200">
                        Aún no hay snapshot del mes anterior: lo que ves es la selección vigente de{' '}
                        {monthLabelEs(month)}. Descarga su snapshot JSON este mes y cárgalo aquí el mes
                        que viene para ver qué entra y qué sale, con el motivo de cada cambio.
                    </p>
                </Card>
            )}

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <Card className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                    <div className="mb-3 flex items-center gap-2">
                        <h4 className="text-sm font-semibold text-gray-200">Entran</h4>
                        <Badge variant="outline" className="border-green-500/50 text-green-300">
                            {formatNumber(diff.entered.length, { maximumFractionDigits: 0 })}
                        </Badge>
                    </div>
                    <MoveList moves={diff.entered} tone="in" />
                </Card>
                <Card className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                    <div className="mb-3 flex items-center gap-2">
                        <h4 className="text-sm font-semibold text-gray-200">Salen</h4>
                        <Badge variant="outline" className="border-red-500/50 text-red-300">
                            {formatNumber(diff.exited.length, { maximumFractionDigits: 0 })}
                        </Badge>
                    </div>
                    <MoveList moves={diff.exited} tone="out" />
                </Card>
            </div>

            {diff.hasPrevious && (
                <Card className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                    <p className="text-sm text-gray-400">
                        Se mantienen {formatNumber(diff.kept.length, { maximumFractionDigits: 0 })} valores
                        {diff.kept.length > 0 && (
                            <>: <span className="text-gray-300">{diff.kept.join(', ')}</span></>
                        )}
                        .
                    </p>
                </Card>
            )}
        </div>
    );
}

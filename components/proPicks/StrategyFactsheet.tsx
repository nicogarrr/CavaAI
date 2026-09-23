'use client';

import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { WalkForwardBacktestResult } from '@/lib/actions/propicks-backtest.actions';

/** La ficha acepta el backtest walk-forward point-in-time (métricas en español). */
export type FactsheetBacktest = WalkForwardBacktestResult | null | undefined;

interface StrategyFactsheetProps {
    strategyId: string;
    name: string;
    description: string;
    /** false cuando el servidor aún no provee esta estrategia. */
    available: boolean;
    backtest?: FactsheetBacktest;
    loading?: boolean;
    error?: string | null;
}

function netMetrics(backtest: FactsheetBacktest) {
    // Walk-forward trae las métricas netas a nivel raíz y en español.
    const wf = (backtest ?? {}) as Partial<WalkForwardBacktestResult>;
    return {
        retorno: wf.retornoNeto ?? undefined,
        benchmark: wf.spy ?? undefined,
        alpha: undefined as number | undefined,
        sharpe: wf.sharpe ?? undefined,
        maxDD: wf.maxDD ?? undefined,
        turnover: wf.turnover ?? undefined,
        period:
            wf.tablaMensual && wf.tablaMensual.length > 0
                ? {
                      start: wf.tablaMensual[0].asOf,
                      end: wf.tablaMensual[wf.tablaMensual.length - 1].asOf,
                  }
                : undefined,
    };
}

function Metric({
    label,
    value,
    footnote,
}: {
    label: string;
    value: string | undefined;
    footnote?: string;
}) {
    return (
        <div className="rounded-lg border border-gray-700/50 bg-gray-900/50 p-3">
            <div className="mb-1 text-xs text-gray-500">{label}</div>
            {value !== undefined ? (
                <div className="text-lg font-bold text-gray-100">{value}</div>
            ) : (
                <div className="text-sm font-medium text-gray-500">Sin datos</div>
            )}
            {footnote && <div className="mt-1 text-[11px] text-gray-500">{footnote}</div>}
        </div>
    );
}

const fmtPct = (v: number | undefined, digits = 2) =>
    v === undefined ? undefined : `${v > 0 ? '+' : ''}${v.toFixed(digits)} %`;

/**
 * Ficha pública de una estrategia: métricas NETAS de costes cuando el backtest
 * las provee, y estado «sin datos» honesto cuando no hay nada que mostrar.
 */
export default function StrategyFactsheet({
    strategyId,
    name,
    description,
    available,
    backtest,
    loading,
    error,
}: StrategyFactsheetProps) {
    if (!available) {
        return (
            <Card className="rounded-lg border border-gray-700 bg-gray-800/50 p-6 text-center">
                <Badge variant="outline" className="mb-3 border-amber-500/50 text-amber-300">
                    Sin datos
                </Badge>
                <h3 className="text-lg font-semibold text-gray-100">{name}</h3>
                <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-gray-400">{description}</p>
                <p className="mx-auto mt-3 max-w-xl text-xs leading-5 text-gray-500">
                    Esta estrategia aún no tiene selección ni backtest publicados. En cuanto estén
                    disponibles aparecerán aquí sus métricas netas de costes. Identificador: {strategyId}.
                </p>
            </Card>
        );
    }

    if (loading && !backtest) {
        return (
            <Card className="rounded-lg border border-gray-700 bg-gray-800/50 p-6 text-center">
                <p className="text-sm text-gray-400">Calculando métricas de {name}…</p>
            </Card>
        );
    }

    const hasWalkForward =
        !!backtest && 'retornoNeto' in backtest && typeof backtest.retornoNeto === 'number';

    if ((error && !backtest) || !hasWalkForward) {
        return (
            <Card className="rounded-lg border border-gray-700 bg-gray-800/50 p-6 text-center">
                <Badge variant="outline" className="mb-3 border-amber-500/50 text-amber-300">
                    Sin datos
                </Badge>
                <h3 className="text-lg font-semibold text-gray-100">{name}</h3>
                <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-gray-400">{description}</p>
                <p className="mx-auto mt-3 max-w-xl text-xs leading-5 text-gray-500">
                    {error ??
                        'El backtest por estrategia se publicará cuando existan fundamentales point-in-time; mientras tanto, el backtest walk-forward global está en la pestaña Backtesting.'}{' '}
                    Los números solo se publican cuando hay datos reales que los respalden.
                </p>
            </Card>
        );
    }

    const m = netMetrics(backtest);
    const period = m.period;

    return (
        <Card className="rounded-lg border border-gray-700 bg-gray-800/50 p-4 sm:p-6">
            <div className="mb-1 flex flex-wrap items-center gap-2">
                <h3 className="text-lg font-semibold text-gray-100">{name}</h3>
                <Badge variant="outline" className="border-teal-500/50 text-teal-300">
                    Backtest neto de costes
                </Badge>
            </div>
            <p className="text-sm leading-6 text-gray-400">{description}</p>
            <p className="mt-1 text-xs text-gray-500">
                Período:{' '}
                {period?.start ? new Date(period.start).toLocaleDateString('es-ES') : '—'} —{' '}
                {period?.end ? new Date(period.end).toLocaleDateString('es-ES') : '—'}
            </p>
            <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3">
                <Metric label="Retorno neto" value={fmtPct(m.retorno)} footnote="Descontados los costes" />
                <Metric label="SPY (referencia)" value={fmtPct(m.benchmark)} footnote="Mismo período" />
                <Metric label="Sharpe neto" value={m.sharpe === undefined ? undefined : m.sharpe.toFixed(2)} />
                <Metric
                    label="Caída máxima neta"
                    value={m.maxDD === undefined ? undefined : `${m.maxDD.toFixed(2)} %`}
                />
                <Metric
                    label="Rotación media"
                    value={m.turnover === undefined ? undefined : `${m.turnover.toFixed(0)} %`}
                    footnote="Turnover"
                />
                <Metric label="Exceso vs SPY (alpha)" value={fmtPct(m.alpha)} />
            </div>
            <p className="mt-4 text-xs leading-5 text-gray-500">
                «Sin datos» significa que el backtest aún no provee esa métrica neta: se publica
                solo lo medido, nunca una estimación disfrazada de dato.
            </p>
        </Card>
    );
}

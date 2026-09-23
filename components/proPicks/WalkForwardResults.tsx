'use client';

import { Card } from '@/components/ui/card';
import { BarChart3, Target } from 'lucide-react';
import type { WalkForwardBacktestResult } from '@/lib/actions/propicks-backtest.actions';

interface WalkForwardResultsProps {
    result: WalkForwardBacktestResult;
}

const fmtPct = (v: number, digits = 2) => `${v > 0 ? '+' : ''}${v.toFixed(digits)}%`;
const signedClass = (v: number) => (v > 0 ? 'text-green-400' : 'text-red-400');

function Metric({ label, value, footnote }: { label: string; value: string; footnote?: string }) {
    return (
        <div className="rounded-lg border border-gray-700/50 bg-gray-900/50 p-3">
            <div className="mb-1 text-xs text-gray-500">{label}</div>
            <div className="text-lg font-bold text-gray-100">{value}</div>
            {footnote && <div className="mt-1 text-[11px] text-gray-500">{footnote}</div>}
        </div>
    );
}

export default function WalkForwardResults({ result }: WalkForwardResultsProps) {
    const first = result.tablaMensual[0];
    const last = result.tablaMensual[result.tablaMensual.length - 1];

    return (
        <Card className="w-full min-w-0 overflow-hidden rounded-lg border border-gray-700 bg-gray-800/50 p-4 sm:p-6">
            <div className="mb-6">
                <div className="mb-2 flex items-center gap-3">
                    <BarChart3 className="h-6 w-6 text-teal-400" />
                    <h3 className="text-xl font-bold text-gray-100">Backtest walk-forward point-in-time</h3>
                </div>
                <p className="text-sm text-gray-400">
                    {result.months} meses simulados, {result.picksPorMes} picks por mes, selección
                    mensual solo con datos anteriores a cada corte.
                </p>
                {first && last && (
                    <p className="mt-2 text-xs text-gray-500">
                        Período: {new Date(first.asOf).toLocaleDateString('es-ES')} -{' '}
                        {new Date(last.asOf).toLocaleDateString('es-ES')}
                    </p>
                )}
            </div>

            <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3">
                <Metric label="Retorno neto" value={fmtPct(result.retornoNeto)} footnote="Compuesto, descontados costes (15 pb/pata)" />
                <Metric label="Retorno bruto" value={fmtPct(result.retornoBruto)} footnote="Antes de costes" />
                <Metric label="SPY (mismo periodo)" value={fmtPct(result.spy)} footnote="Buy & hold" />
                <Metric label="Sharpe" value={result.sharpe.toFixed(2)} />
                <Metric label="Sortino" value={result.sortino.toFixed(2)} />
                <Metric label="Máx. drawdown" value={`${result.maxDD.toFixed(2)}%`} footnote="Sobre la curva neta" />
            </div>

            <div className="mb-6 min-w-0">
                <h4 className="mb-3 text-sm font-semibold text-gray-300">Desempeño mensual</h4>
                <div className="hidden overflow-x-auto md:block">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-gray-700">
                                <th className="py-2 text-left text-gray-400">Corte</th>
                                <th className="py-2 text-left text-gray-400">Picks</th>
                                <th className="py-2 text-right text-gray-400">Mes neto</th>
                                <th className="py-2 text-right text-gray-400">SPY</th>
                                <th className="py-2 text-right text-gray-400">Rotación</th>
                            </tr>
                        </thead>
                        <tbody>
                            {result.tablaMensual.map((row) => (
                                <tr key={row.asOf} className="border-b border-gray-700/50">
                                    <td className="py-2 text-gray-300">{new Date(row.asOf).toLocaleDateString('es-ES')}</td>
                                    <td className="py-2 text-gray-400">{row.picks.join(', ')}</td>
                                    <td className={`py-2 text-right font-bold ${signedClass(row.retNeto)}`}>{fmtPct(row.retNeto)}</td>
                                    <td className={`py-2 text-right ${signedClass(row.spy)}`}>{fmtPct(row.spy)}</td>
                                    <td className="py-2 text-right text-gray-400">{row.turnover.toFixed(0)}%</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                <div className="grid grid-cols-1 gap-3 md:hidden">
                    {result.tablaMensual.map((row) => (
                        <div key={row.asOf} className="min-w-0 rounded-lg border border-gray-700/50 bg-gray-900/50 p-4">
                            <div className="flex items-center justify-between gap-2">
                                <span className="font-medium text-gray-200">{new Date(row.asOf).toLocaleDateString('es-ES')}</span>
                                <span className={`shrink-0 font-bold ${signedClass(row.retNeto)}`}>{fmtPct(row.retNeto)}</span>
                            </div>
                            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
                                <span className="min-w-0 truncate">{row.picks.join(', ')}</span>
                                <span>SPY {fmtPct(row.spy)}</span>
                                <span>Rotación {row.turnover.toFixed(0)}%</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <div className="rounded-lg border border-gray-700/50 bg-gray-900/50 p-4">
                <div className="mb-3 flex items-center gap-2">
                    <Target className="h-4 w-4 text-teal-400" />
                    <h4 className="text-sm font-semibold text-gray-300">Metodología</h4>
                </div>
                <ul className="list-disc space-y-1 pl-5 text-xs leading-5 text-gray-400">
                    <li>Walk-forward mensual: cada corte usa únicamente precios de cierre anteriores a ese corte (sin datos futuros).</li>
                    <li>Señal: momentum 12-1M (se excluye el último mes) sobre un universo líquido de 30 valores; {result.picksPorMes} picks equiponderados.</li>
                    <li>Costes aplicados: 15 pb por pata de rotación. Rotación media mensual: {result.turnover.toFixed(0)}%.</li>
                    <li>Benchmark: SPY buy & hold en el mismo periodo.</li>
                    <li>Resultados pasados simulados no garantizan rendimientos futuros. Esto no es asesoramiento financiero.</li>
                </ul>
            </div>
        </Card>
    );
}

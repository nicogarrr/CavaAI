'use client';

import { Card } from '@/components/ui/card';
import { formatBacktestResult, type BacktestResult } from '@/lib/utils/backtesting';
import { TrendingUp, TrendingDown, BarChart3, Target } from 'lucide-react';

interface BacktestResultsProps {
    result: BacktestResult;
}

export default function BacktestResults({ result }: BacktestResultsProps) {
    const { summary, details } = formatBacktestResult(result);

    return (
        <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
            <div className="mb-6">
                <div className="flex items-center gap-3 mb-2">
                    <BarChart3 className="h-6 w-6 text-teal-400" />
                    <h3 className="text-xl font-bold text-gray-100">Resultados de Backtesting</h3>
                </div>
                <p className="text-sm text-gray-400">{summary}</p>
                <p className="text-xs text-gray-500 mt-2">
                    Período: {new Date(result.period.start).toLocaleDateString('es-ES')} - {new Date(result.period.end).toLocaleDateString('es-ES')}
                </p>
            </div>

            {/* Métricas principales */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
                {details.map((detail, index) => (
                    <div key={index} className="p-3 bg-gray-900/50 rounded-lg border border-gray-700/50">
                        <div className="text-xs text-gray-500 mb-1">{detail.label}</div>
                        <div className={`text-lg font-bold ${detail.color}`}>
                            {detail.value}
                        </div>
                    </div>
                ))}
            </div>

            {/* Tabla de picks */}
            <div className="mb-6">
                <h4 className="text-sm font-semibold text-gray-300 mb-3">Desempeño Individual</h4>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-gray-700">
                                <th className="text-left py-2 text-gray-400">Símbolo</th>
                                <th className="text-right py-2 text-gray-400">Entrada</th>
                                <th className="text-right py-2 text-gray-400">Salida</th>
                                <th className="text-right py-2 text-gray-400">Retorno</th>
                                <th className="text-right py-2 text-gray-400">Días</th>
                            </tr>
                        </thead>
                        <tbody>
                            {result.picks.slice(0, 10).map((pick, index) => (
                                <tr key={index} className="border-b border-gray-700/50">
                                    <td className="py-2 text-gray-300 font-medium">{pick.symbol}</td>
                                    <td className="py-2 text-right text-gray-400">${pick.entryPrice.toFixed(2)}</td>
                                    <td className="py-2 text-right text-gray-400">${pick.exitPrice.toFixed(2)}</td>
                                    <td className={`py-2 text-right font-bold ${pick.return > 0 ? 'text-green-400' : 'text-red-400'}`}>
                                        {pick.return > 0 ? '+' : ''}{pick.return.toFixed(2)}%
                                    </td>
                                    <td className="py-2 text-right text-gray-400">{pick.holdPeriod}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Resumen de benchmark */}
            <div className="p-4 bg-gray-900/50 rounded-lg border border-gray-700/50">
                <div className="flex items-center gap-2 mb-3">
                    <Target className="h-4 w-4 text-teal-400" />
                    <h4 className="text-sm font-semibold text-gray-300">Comparación con Benchmark</h4>
                </div>
                <div className="grid grid-cols-3 gap-4">
                    <div>
                        <div className="text-xs text-gray-500 mb-1">Retorno Estrategia</div>
                        <div className={`text-lg font-bold ${result.performance.totalReturn > 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {result.performance.totalReturn > 0 ? '+' : ''}{result.performance.totalReturn.toFixed(2)}%
                        </div>
                    </div>
                    <div>
                        <div className="text-xs text-gray-500 mb-1">Retorno S&P 500</div>
                        <div className={`text-lg font-bold ${result.vsBenchmark.benchmarkReturn > 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {result.vsBenchmark.benchmarkReturn > 0 ? '+' : ''}{result.vsBenchmark.benchmarkReturn.toFixed(2)}%
                        </div>
                    </div>
                    <div>
                        <div className="text-xs text-gray-500 mb-1">Alpha (Exceso)</div>
                        <div className={`text-lg font-bold ${result.vsBenchmark.alpha > 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {result.vsBenchmark.alpha > 0 ? '+' : ''}{result.vsBenchmark.alpha.toFixed(2)}%
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    );
}


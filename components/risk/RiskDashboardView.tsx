'use client';

import Link from 'next/link';
import { Briefcase, Gauge } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { RecordDetail, formatRecordValue, type DataRecord } from '@/components/data/RecordViews';
import { getRiskDashboard } from '@/lib/actions/risk.actions';

interface RiskDashboardViewProps {
    initialDashboard: DataRecord | null;
}

function extractPositions(dashboard: DataRecord | null): DataRecord[] {
    if (!dashboard) return [];
    const raw = dashboard.positions;
    if (!Array.isArray(raw)) return [];
    return raw.filter(
        (item): item is DataRecord =>
            item !== null && typeof item === 'object' && !Array.isArray(item),
    );
}

function extractAlerts(dashboard: DataRecord | null): DataRecord[] {
    if (!dashboard) return [];
    const raw = dashboard.alerts;
    if (!Array.isArray(raw)) return [];
    return raw.filter(
        (item): item is DataRecord =>
            item !== null && typeof item === 'object' && !Array.isArray(item),
    );
}

/**
 * Explicación didáctica del umbral que dispara cada alerta. El motor solo
 * aplica reglas de concentración y liquidez (portfolio_risk.py): sin VaR ni
 * drawdown, y aquí se dice junto a cada alerta.
 */
function thresholdExplanation(alert: DataRecord): string {
    const threshold = alert.threshold;
    if (threshold === 0.2) {
        return 'Umbral 20% del valor de la cartera: por encima, una sola posición concentra el riesgo y si falla arrastra gran parte del resultado. Es una regla de concentración simple y verificable, no un VaR ni una probabilidad de pérdida.';
    }
    if (threshold === 0.1) {
        return 'Umbral 10%: las empresas «pre-FCF» todavía no generan caja libre, así que el límite es el doble de estricto que el 20% general. Regla de prudencia sobre fragilidad financiera, no una predicción de caída.';
    }
    if (threshold === 0) {
        return 'La caja de esta divisa está en negativo (saldo deudor, típicamente préstamo sobre margen). Revisa los saldos o las operaciones en esa divisa; el umbral es no bajar de cero.';
    }
    return 'Alerta disparada al superar el umbral indicado junto al valor medido.';
}

/** Resumen sin arrays anidados (positions/alerts se muestran en su propia tabla) */
function headlineRecord(dashboard: DataRecord | null): DataRecord | null {
    if (!dashboard) return null;
    const { positions: _positions, alerts: _alerts, ...rest } = dashboard;
    void _positions;
    void _alerts;
    return rest;
}

function weightText(position: DataRecord): string {
    const weight = position.weight;
    if (typeof weight === 'number' && Number.isFinite(weight)) {
        return `${(weight * 100).toFixed(2)}%`;
    }
    return '—';
}

export default function RiskDashboardView({ initialDashboard }: RiskDashboardViewProps) {
    const positions = extractPositions(initialDashboard);
    const alerts = extractAlerts(initialDashboard);

    return (
        <div className="grid gap-6">
            <RecordDetail
                title="Dashboard de Riesgo"
                description="Estructura de la cartera: pesos, concentración (top 1 y top 5) y exposición por sector y factor. No calcula VaR, drawdown ni volatilidad: hace falta historia de precios que el motor aún no usa."
                icon={<Gauge className="h-5 w-5 text-teal-400" />}
                record={headlineRecord(initialDashboard)}
                fetchRecord={async () => headlineRecord(await getRiskDashboard())}
                maxKeys={32}
                emptyMessage="No hay métricas de riesgo disponibles. Comprueba que tu cartera tiene posiciones."
            />

            <Card className="rounded-lg border border-gray-700 bg-gray-800/50">
                <CardHeader className="border-b border-gray-700/50 pb-4">
                    <div className="flex items-center gap-3">
                        <Gauge className="h-5 w-5 text-teal-400" />
                        <div>
                            <CardTitle className="text-lg font-semibold text-gray-100">
                                Alertas de concentración y liquidez
                            </CardTitle>
                            <CardDescription className="mt-0.5 text-sm text-gray-500">
                                Reglas de peso y saldo; cada alerta explica el umbral que la dispara
                            </CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="pt-4">
                    {alerts.length === 0 ? (
                        <p className="py-6 text-center text-sm text-gray-500">
                            Sin alertas: ninguna posición supera los umbrales de peso (20% del cartera en una
                            posición, 10% en empresas pre-FCF) y no hay caja negativa por divisa.
                        </p>
                    ) : (
                        <div className="space-y-3">
                            {alerts.map((alert, index) => (
                                <div className="rounded-md border border-gray-700/60 bg-black/20 p-3" key={index}>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <Badge variant="outline">{formatRecordValue(alert.severity)}</Badge>
                                        <span className="text-sm text-gray-200">{formatRecordValue(alert.message)}</span>
                                    </div>
                                    <p className="mt-2 text-xs leading-5 text-gray-400">{thresholdExplanation(alert)}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            <Card className="rounded-lg border border-gray-700 bg-gray-800/50">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-gray-700/50 pb-4">
                    <div className="flex items-center gap-3">
                        <Briefcase className="h-5 w-5 text-teal-400" />
                        <div>
                            <CardTitle className="text-lg font-semibold text-gray-100">
                                Exposición por posición
                            </CardTitle>
                            <CardDescription className="mt-0.5 text-sm text-gray-500">
                                Cada holding enlaza a su ficha de research
                            </CardDescription>
                        </div>
                    </div>
                    <Link
                        href="/portfolio"
                        className="text-sm font-semibold text-teal-300 hover:text-teal-200"
                    >
                        Ver cartera →
                    </Link>
                </CardHeader>
                <CardContent className="pt-4">
                    {positions.length === 0 ? (
                        <p className="py-10 text-center text-sm text-gray-500">
                            Sin posiciones con exposición calculada.
                        </p>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow className="border-gray-700 hover:bg-transparent">
                                    <TableHead className="text-xs font-semibold uppercase text-gray-500">Ticker</TableHead>
                                    <TableHead className="text-xs font-semibold uppercase text-gray-500">Nombre</TableHead>
                                    <TableHead className="text-xs font-semibold uppercase text-gray-500">Sector</TableHead>
                                    <TableHead className="text-right text-xs font-semibold uppercase text-gray-500">Valor</TableHead>
                                    <TableHead className="text-right text-xs font-semibold uppercase text-gray-500">Peso</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {positions.map((position, index) => {
                                    const ticker = position.ticker;
                                    const href =
                                        typeof ticker === 'string' && ticker.trim()
                                            ? `/research/${encodeURIComponent(ticker.trim().toUpperCase())}`
                                            : null;
                                    return (
                                        <TableRow key={index} className="border-gray-700/50">
                                            <TableCell>
                                                {href ? (
                                                    <Link
                                                        href={href}
                                                        className="font-mono font-bold text-teal-300 hover:text-teal-200 hover:underline"
                                                    >
                                                        {formatRecordValue(ticker)}
                                                    </Link>
                                                ) : (
                                                    <span className="font-mono text-gray-300">
                                                        {formatRecordValue(ticker)}
                                                    </span>
                                                )}
                                            </TableCell>
                                            <TableCell className="text-sm text-gray-300">
                                                {formatRecordValue(position.name)}
                                            </TableCell>
                                            <TableCell className="text-sm text-gray-400">
                                                {formatRecordValue(position.sector)}
                                            </TableCell>
                                            <TableCell className="text-right text-sm text-gray-200">
                                                {formatRecordValue(position.market_value)}
                                            </TableCell>
                                            <TableCell className="text-right text-sm font-semibold text-gray-100">
                                                {weightText(position)}
                                            </TableCell>
                                        </TableRow>
                                    );
                                })}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}

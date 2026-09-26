'use client';

import { useState, type ReactNode } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Inbox, Loader2, RefreshCw } from 'lucide-react';
import { showErrorToast } from '@/lib/toast';

export type DataRecord = Record<string, unknown>;

/** Convierte cualquier valor a texto plano legible en tabla/cards */
export function formatRecordValue(value: unknown): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? 'Sí' : 'No';
    if (typeof value === 'object') {
        try {
            return JSON.stringify(value);
        } catch {
            return String(value);
        }
    }
    return String(value);
}

/** Normaliza un array de respuestas a DataRecord[] (los primitivos se envuelven) */
export function toRecords(data: unknown[]): DataRecord[] {
    return data.map((item) => (
        item !== null && typeof item === 'object' && !Array.isArray(item)
            ? item as DataRecord
            : { value: item }
    ));
}

/** Selecciona columnas legibles: claves planas (sin objetos anidados), máx 6, con preferencia explícita */
export function pickColumns(records: DataRecord[], preferred?: string[]): string[] {
    if (preferred && preferred.length > 0) return preferred;
    const keys: string[] = [];
    for (const record of records.slice(0, 3)) {
        for (const key of Object.keys(record)) {
            if (keys.includes(key)) continue;
            const value = record[key];
            if (value !== null && typeof value === 'object') continue;
            keys.push(key);
        }
        if (keys.length >= 6) break;
    }
    return keys;
}

/** Construye el href a /research/[ticker] desde la clave `ticker` del registro (o null si no hay) */
export function researchHrefFor(record: DataRecord, key = 'ticker'): string | null {
    const value = record[key];
    if (typeof value !== 'string' || !value.trim()) return null;
    return `/research/${encodeURIComponent(value.trim().toUpperCase())}`;
}

export interface RecordListProps {
    title: string;
    description?: string;
    icon?: ReactNode;
    /** Datos iniciales recibidos desde el servidor */
    records: DataRecord[];
    /** Server action que devuelve el listado (para refresco client-side) */
    fetchRecords: () => Promise<unknown[]>;
    /** Columnas explícitas; si se omite se infieren de los datos */
    columns?: string[];
    emptyMessage?: string;
    /** CTA del estado vacío (primer paso: crear, importar, ir a...) */
    emptyAction?: ReactNode;
    /** Acciones por fila (botón Aplicar, eliminar, etc.) */
    rowActions?: (record: DataRecord, index: number) => ReactNode;
    /** Columnas cuyo valor se renderiza como enlace (p.ej. ticker -> /research/[ticker]) */
    linkColumns?: Record<string, (record: DataRecord, index: number) => string | null | undefined>;
    footer?: ReactNode;
}

export function RecordList({
    title,
    description,
    icon,
    records: initialRecords,
    fetchRecords,
    columns,
    emptyMessage = 'No hay datos disponibles todavía',
    emptyAction,
    rowActions,
    linkColumns,
    footer,
}: RecordListProps) {
    const [records, setRecords] = useState<DataRecord[]>(initialRecords);
    const [loading, setLoading] = useState(false);

    const refresh = async () => {
        setLoading(true);
        try {
            const data = await fetchRecords();
            setRecords(toRecords(data));
        } catch (error) {
            showErrorToast(error, { onRetry: refresh });
        } finally {
            setLoading(false);
        }
    };

    const visibleColumns = pickColumns(records, columns);

    return (
        <Card className="rounded-lg border border-gray-700">
            <CardHeader className="flex flex-col gap-3 border-b border-gray-700/50 pb-4 sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
                <div className="flex items-center gap-3">
                    {icon}
                    <div>
                        <CardTitle className="text-lg font-semibold text-gray-100">{title}</CardTitle>
                        {description && <CardDescription className="mt-0.5 text-sm text-gray-500">{description}</CardDescription>}
                    </div>
                </div>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={refresh}
                    disabled={loading}
                    className="gap-2 text-gray-400 hover:text-teal-400"
                >
                    <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    Refrescar
                </Button>
            </CardHeader>
            <CardContent className="pt-4">
                {loading && records.length === 0 ? (
                    <div className="flex items-center justify-center py-10 text-gray-500">
                        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Cargando...
                    </div>
                ) : records.length === 0 ? (
                    <EmptyState action={emptyAction} icon={Inbox} title={emptyMessage} />
                ) : visibleColumns.length === 0 ? (
                    <div className="space-y-2">
                        {records.map((record, index) => (
                            <pre key={index} className="overflow-x-auto rounded border border-gray-700/50 bg-surface-0/50 p-3 text-xs text-gray-400">
                                {JSON.stringify(record, null, 2)}
                            </pre>
                        ))}
                    </div>
                ) : (
                    <Table>
                        <TableHeader>
                            <TableRow className="border-gray-700 hover:bg-transparent">
                                {visibleColumns.map((column) => (
                                    <TableHead key={column} className="text-xs font-semibold uppercase text-gray-500">
                                        {column}
                                    </TableHead>
                                ))}
                                {rowActions && <TableHead className="text-right text-xs font-semibold uppercase text-gray-500">Acciones</TableHead>}
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {records.map((record, index) => (
                                <TableRow key={index} className="border-gray-700/50">
                                    {visibleColumns.map((column) => {
                                        const href = linkColumns?.[column]?.(record, index);
                                        return (
                                            <TableCell key={column} className="text-sm text-gray-300">
                                                {href ? (
                                                    <Link
                                                        href={href}
                                                        className="font-mono font-semibold text-teal-300 hover:text-teal-200 hover:underline"
                                                    >
                                                        {formatRecordValue(record[column])}
                                                    </Link>
                                                ) : (
                                                    <span className="line-clamp-3">{formatRecordValue(record[column])}</span>
                                                )}
                                            </TableCell>
                                        );
                                    })}
                                    {rowActions && (
                                        <TableCell className="text-right">
                                            {rowActions(record, index)}
                                        </TableCell>
                                    )}
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                )}
                {footer && <div className="mt-4">{footer}</div>}
            </CardContent>
        </Card>
    );
}

export interface RecordDetailProps {
    title: string;
    description?: string;
    icon?: ReactNode;
    record: DataRecord | null;
    fetchRecord?: () => Promise<unknown>;
    emptyMessage?: string;
    /** CTA del estado vacío (primer paso: crear, importar, ir a...) */
    emptyAction?: ReactNode;
    /** Contenido adicional (botones de acción sobre el objeto, p.ej. regenerar) */
    actions?: ReactNode;
    /** Máximo de claves a mostrar; por defecto todas */
    maxKeys?: number;
    /** Claves internas/debug que no se muestran (p.ej. trace del backend). */
    hiddenKeys?: string[];
}

/** Tarjeta clave/valor para respuestas de objeto único (plan, drift, risk dashboard, reporte fiscal...) */
export function RecordDetail({
    title,
    description,
    icon,
    record,
    fetchRecord,
    emptyMessage = 'No hay datos disponibles todavía',
    emptyAction,
    actions,
    maxKeys = 24,
    hiddenKeys,
}: RecordDetailProps) {
    const [data, setData] = useState<DataRecord | null>(record);

    const refresh = async () => {
        if (!fetchRecord) return;
        try {
            const result = await fetchRecord();
            if (result === null) {
                // null = estado vacío honesto (p.ej. plan sin configurar)
                setData(null);
            } else if (typeof result === 'object' && !Array.isArray(result)) {
                setData(result as DataRecord);
            }
        } catch (error) {
            showErrorToast(error, { onRetry: refresh });
        }
    };

    const hidden = new Set((hiddenKeys ?? []).map((key) => key.toLowerCase()));
    const entries = data
        ? Object.entries(data)
              .filter(([key]) => !hidden.has(key.toLowerCase()))
              .slice(0, maxKeys)
        : [];

    return (
        <Card className="rounded-lg border border-gray-700">
            <CardHeader className="flex flex-col gap-3 border-b border-gray-700/50 pb-4 sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
                <div className="flex items-center gap-3">
                    {icon}
                    <div>
                        <CardTitle className="text-lg font-semibold text-gray-100">{title}</CardTitle>
                        {description && <CardDescription className="mt-0.5 text-sm text-gray-500">{description}</CardDescription>}
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {fetchRecord && (
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={refresh}
                            className="gap-2 text-gray-400 hover:text-teal-400"
                        >
                            <RefreshCw className="h-4 w-4" />
                            Refrescar
                        </Button>
                    )}
                    {actions}
                </div>
            </CardHeader>
            <CardContent className="pt-4">
                {!data || entries.length === 0 ? (
                    <EmptyState action={emptyAction} icon={Inbox} title={emptyMessage} />
                ) : (
                    <div className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-gray-700/50 bg-gray-700/40 sm:grid-cols-2">
                        {entries.map(([key, value]) => (
                            <div key={key} className="flex flex-col gap-1 bg-surface-0/60 p-3">
                                <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">{key}</span>
                                <span className="break-words text-sm text-gray-200">
                                    <span className="line-clamp-4">{formatRecordValue(value)}</span>
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
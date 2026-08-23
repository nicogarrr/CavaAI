'use client';

import { useCallback, useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Inbox, Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { getErrorMessage } from '@/lib/types/errors';

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
    /** Acciones por fila (botón Aplicar, eliminar, etc.) */
    rowActions?: (record: DataRecord, index: number) => ReactNode;
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
    rowActions,
    footer,
}: RecordListProps) {
    const [records, setRecords] = useState<DataRecord[]>(initialRecords);
    const [loading, setLoading] = useState(false);

    const refresh = useCallback(async () => {
        setLoading(true);
        try {
            const data = await fetchRecords();
            setRecords(toRecords(data));
        } catch (error) {
            toast.error(getErrorMessage(error));
        } finally {
            setLoading(false);
        }
    }, [fetchRecords]);

    const visibleColumns = pickColumns(records, columns);

    return (
        <Card className="rounded-lg border border-gray-700 bg-gray-800/50">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-gray-700/50 pb-4">
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
                    <div className="py-10 text-center text-gray-500">
                        <Inbox className="mx-auto mb-3 h-10 w-10 text-gray-600" />
                        <p className="text-sm">{emptyMessage}</p>
                    </div>
                ) : visibleColumns.length === 0 ? (
                    <div className="space-y-2">
                        {records.map((record, index) => (
                            <pre key={index} className="overflow-x-auto rounded border border-gray-700/50 bg-gray-900/50 p-3 text-xs text-gray-400">
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
                                    {visibleColumns.map((column) => (
                                        <TableCell key={column} className="text-sm text-gray-300">
                                            <span className="line-clamp-3">{formatRecordValue(record[column])}</span>
                                        </TableCell>
                                    ))}
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
    /** Contenido adicional (botones de acción sobre el objeto, p.ej. regenerar) */
    actions?: ReactNode;
    /** Máximo de claves a mostrar; por defecto todas */
    maxKeys?: number;
}

/** Tarjeta clave/valor para respuestas de objeto único (plan, drift, risk dashboard, reporte fiscal...) */
export function RecordDetail({
    title,
    description,
    icon,
    record,
    fetchRecord,
    emptyMessage = 'No hay datos disponibles todavía',
    actions,
    maxKeys = 24,
}: RecordDetailProps) {
    const [data, setData] = useState<DataRecord | null>(record);

    const refresh = useCallback(async () => {
        if (!fetchRecord) return;
        try {
            const result = await fetchRecord();
            if (result !== null && typeof result === 'object' && !Array.isArray(result)) {
                setData(result as DataRecord);
            }
        } catch (error) {
            toast.error(getErrorMessage(error));
        }
    }, [fetchRecord]);

    const entries = data ? Object.entries(data).slice(0, maxKeys) : [];

    return (
        <Card className="rounded-lg border border-gray-700 bg-gray-800/50">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-gray-700/50 pb-4">
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
                    <div className="py-10 text-center text-gray-500">
                        <Inbox className="mx-auto mb-3 h-10 w-10 text-gray-600" />
                        <p className="text-sm">{emptyMessage}</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-gray-700/50 bg-gray-700/40 sm:grid-cols-2">
                        {entries.map(([key, value]) => (
                            <div key={key} className="flex flex-col gap-1 bg-gray-900/60 p-3">
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
'use server';

import { researchIdentityHeaders } from '@/lib/auth/research-identity';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { AppError } from '@/lib/types/errors';

const BACKEND_URL = process.env.FMP_BACKEND_URL ?? 'http://localhost:8000';

export type ExportFormat = 'csv' | 'json';

export interface ExportResult {
    filename: string;
    contentType: string;
    content: string;
}

/**
 * GET /api/export/{year}?format=csv|json
 * Exportación anual del journal de decisiones (CSV o JSON descargable).
 * Se lee el cuerpo como texto para soportar respuestas CSV y JSON por igual.
 */
export async function exportJournal(year: number, format: ExportFormat = 'csv'): Promise<ExportResult> {
    await requireAuthenticatedUser();
    if (!Number.isInteger(year) || year < 2000 || year > 2100) {
        throw new AppError('Año de exportación inválido', 'VALIDATION_ERROR', 400);
    }

    // `format` es una union de TypeScript: no valida nada en runtime.
    if (format !== 'csv' && format !== 'json') {
        throw new AppError('Formato de exportación inválido', 'VALIDATION_ERROR', 400);
    }

    // La peticion sale hacia el backend configurado y nada mas: la URL se
    // construye con el constructor URL, se fija el origen al de BACKEND_URL y
    // los valores que vienen del cliente entran como constantes revalidadas
    // (year acotado arriba; format mapeado a literal). Asi ningun valor
    // remoto puede desviar el fetch a otro host ni inyectar en la query.
    const exportUrl = new URL(`/api/export/${year}`, BACKEND_URL);
    if (exportUrl.origin !== new URL(BACKEND_URL).origin) {
        throw new AppError('Backend de exportación mal configurado', 'CONFIG_ERROR', 500);
    }
    const safeFormat = format === 'csv' ? 'csv' : 'json';
    exportUrl.searchParams.set('format', safeFormat);

    const identityHeaders = await researchIdentityHeaders({
        method: 'GET',
        path: `/api/export/${year}`,
    });
    const response = await fetch(exportUrl, {
        headers: { ...identityHeaders },
        cache: 'no-store',
    });

    if (!response.ok) {
        const detail = await response.text().catch(() => response.statusText);
        throw new AppError(
            `Exportación falló (${response.status}): ${detail.slice(0, 300)}`,
            'RESEARCH_API_ERROR',
            response.status,
        );
    }

    const contentType = response.headers.get('content-type') ?? 'text/plain';
    const content = await response.text();
    const extension = format === 'csv' ? 'csv' : 'json';
    return {
        filename: `journal-${year}.${extension}`,
        contentType,
        content,
    };
}
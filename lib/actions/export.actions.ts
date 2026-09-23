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

    const identityHeaders = await researchIdentityHeaders({
        method: 'GET',
        path: `/api/export/${year}`,
    });
    const response = await fetch(`${BACKEND_URL}/api/export/${year}?format=${format}`, {
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
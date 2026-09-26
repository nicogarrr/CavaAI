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
    // `format` es una union de TypeScript: no valida nada en runtime, y se
    // interpola en la query del engine firmado.
    if (format !== 'csv' && format !== 'json') {
        throw new AppError('Formato de exportación inválido', 'VALIDATION_ERROR', 400);
    }
    const safeFormat = encodeURIComponent(format);
    const identityHeaders = await researchIdentityHeaders({
        method: 'GET',
        path: `/api/export/${year}`,
    });
    const response = await fetch(`${BACKEND_URL}/api/export/${year}?format=${safeFormat}`, {
        headers: { ...identityHeaders },
        cache: 'no-store',
    });

    if (!response.ok) {
        // El cuerpo del engine puede traer un traceback del backend (rutas,
        // SQL, hostnames internos). Se registra en el servidor y al cliente
        // solo se le da el status. Ver ERROR_MESSAGES.EXTERNAL_API_ERROR.
        const detail = await response.text().catch(() => response.statusText);
        console.error(
            `[exportJournal] research engine respondió ${response.status}: ${detail.slice(0, 500)}`,
        );
        throw new AppError(
            `Exportación falló (${response.status})`,
            'RESEARCH_API_ERROR',
            response.status,
        );
    }

    const contentType = response.headers.get('content-type') ?? 'text/plain';
    const content = await response.text();
    const extension = safeFormat === 'csv' ? 'csv' : 'json';
    return {
        filename: `journal-${year}.${extension}`,
        contentType,
        content,
    };
}
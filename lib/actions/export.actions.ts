'use server';

import { researchIdentityHeaders } from '@/lib/auth/research-identity';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { AppError } from '@/lib/types/errors';

const BACKEND_URL = process.env.FMP_BACKEND_URL ?? 'http://localhost:8000';

// Destino fijo: los unicos años exportables son 2000-2100 y cada uno mapea a
// una ruta constante construida desde literales. El valor remoto (`year`)
// solo se usa como clave del mapa, nunca para componer la URL, de modo que
// ningun dato del cliente llega al fetch (CodeQL js/request-forgery).
const EXPORT_PATHS: Readonly<Record<number, string>> = Object.fromEntries(
    Array.from({ length: 101 }, (_, i) => {
        const y = 2000 + i;
        return [y, `/api/export/${y}`];
    }),
);

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
    // La peticion sale hacia el backend configurado y nada mas: la ruta sale
    // del mapa de constantes (year solo actua de clave), se fija el origen al
    // de BACKEND_URL y format entra como literal revalidado.
    const exportPath = EXPORT_PATHS[year];
    const exportUrl = new URL(exportPath, BACKEND_URL);
    if (exportUrl.origin !== new URL(BACKEND_URL).origin) {
        throw new AppError('Backend de exportación mal configurado', 'CONFIG_ERROR', 500);
    }
    const safeFormat = format === 'csv' ? 'csv' : 'json';
    exportUrl.searchParams.set('format', safeFormat);
    const identityHeaders = await researchIdentityHeaders({
        method: 'GET',
        path: exportPath,
    });
    const response = await fetch(exportUrl, {
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
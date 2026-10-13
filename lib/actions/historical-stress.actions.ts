'use server';

import { researchIdentityHeaders } from '@/lib/auth/research-identity';
import { AppError, ExternalAPIError } from '@/lib/types/errors';
import type { HistoricalStressReport } from '@/types/historical-stress';

export async function getHistoricalStress(ticker?: string): Promise<HistoricalStressReport> {
    const params = new URLSearchParams();
    if (ticker) params.set('ticker', ticker);
    const path = `/api/risk/historical-stress?${params}`;
    try {
        const identity = await researchIdentityHeaders({ method: 'GET', path });
        const response = await fetch(`${process.env.FMP_BACKEND_URL ?? 'http://localhost:8000'}${path}`, {
            cache: 'no-store', headers: identity,
        });
        if (!response.ok) throw new AppError('No se pudo calcular el estrés histórico', 'RESEARCH_API_ERROR', response.status);
        return await response.json() as HistoricalStressReport;
    } catch (error) {
        if (error instanceof AppError) throw error;
        throw new ExternalAPIError('No se pudo conectar con el motor de datos', 'research-api', error);
    }
}

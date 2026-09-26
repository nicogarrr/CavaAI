'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchRequest } from '@/lib/research/client';
import { assertYear } from '@/lib/validation/pathParams';

export type TaxRecord = Record<string, unknown>;

/** GET /api/taxes/holdings — posiciones con base de coste para impuestos */
export async function getTaxHoldings(): Promise<TaxRecord[]> {
    await requireAuthenticatedUser();
    return researchRequest<TaxRecord[]>('/api/taxes/holdings');
}

/** GET /api/taxes/report/{fiscal_year} — reporte fiscal anual */
export async function getTaxReport(fiscalYear: number): Promise<TaxRecord> {
    await requireAuthenticatedUser();
    return researchRequest<TaxRecord>(`/api/taxes/report/${assertYear(fiscalYear, 'fiscalYear')}`);
}

/** POST /api/taxes/report/{fiscal_year}/regenerate — regenera el reporte fiscal */
export async function regenerateTaxReport(fiscalYear: number): Promise<TaxRecord> {
    await requireAuthenticatedUser();
    return researchRequest<TaxRecord>(`/api/taxes/report/${assertYear(fiscalYear, 'fiscalYear')}/regenerate`, {
        method: 'POST',
    });
}
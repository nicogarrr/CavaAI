'use server';

import { researchRequest } from '@/lib/research/client';

export type CapitalFact = {
  value: number; unit: string; date: string; fact_id: number;
  source: string; source_url: string; reported_on: string | null;
  source_updated_on: string | null; status: 'OFICIAL'; concept: string | null;
};
export type ShareBalance = CapitalFact & {
  previous_date: string | null; net_change: number | null; net_change_pct: number | null;
  change_status: 'DERIVADO' | 'SIN_DATOS'; split_between_dates: boolean; abrupt_jump?: boolean;
};
export type AnnualCapitalFlow = {
  date: string; shares_repurchased?: CapitalFact; common_stock_repurchased?: CapitalFact;
  common_stock_issued?: CapitalFact; stock_based_compensation?: CapitalFact;
};
export type ShareCapital = {
  ticker: string; status: 'OFICIAL' | 'SIN_DATOS'; as_of: string;
  share_basis: 'reported_unadjusted'; series: ShareBalance[]; annual_flows: AnnualCapitalFlow[];
};
export async function getShareCapital(ticker: string): Promise<ShareCapital> {
  return researchRequest<ShareCapital>(`/api/companies/${encodeURIComponent(ticker)}/share-capital`, { fast: true });
}

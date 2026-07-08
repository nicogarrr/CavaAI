'use server';

import { revalidatePath } from 'next/cache';

const BACKEND_URL = process.env.FMP_BACKEND_URL ?? 'http://localhost:8000';

export type ResearchCompany = {
  id: number;
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  company_type: string;
  valuation_model: string;
  factor_tags: string[];
  special_sources: string[];
  special_risks: string[];
};

export type ResearchPortfolioSummary = {
  total_value: number;
  equity_value: number;
  cash: Record<string, number>;
  top_1_weight: number;
  top_5_weight: number;
  alerts: Array<{
    severity: string;
    ticker: string | null;
    message: string;
    metric_value: number;
    threshold: number;
  }>;
};

export type ResearchWorkflow = {
  name: string;
  input: string;
  steps: string[];
};

export type ResearchSettings = {
  app_env: string;
  maf_version: string;
  budget: {
    daily_cost_eur: number;
    monthly_cost_eur: number;
    daily_cap_eur: number;
    monthly_cap_eur: number;
  };
  connectors: Record<string, boolean | string>;
};

export type ResearchFact = {
  id: number;
  company_id: number;
  metric: string;
  value: string;
  unit: string;
  period: string;
  fiscal_year: number | null;
  fiscal_quarter: string | null;
  source_id: number | null;
  source_type: string;
  is_reported: boolean;
  is_adjusted: boolean;
  confidence: string;
  created_at: string;
};

export type ResearchValuation = {
  ticker: string;
  model_type: string;
  current_price: number;
  bear_value: number;
  base_value: number;
  bull_value: number;
  expected_value: number;
  margin_of_safety: number;
  reverse_dcf: {
    required_revenue_growth?: number;
    solved_value_per_share?: number;
    trace?: Record<string, unknown>;
  };
  sensitivity: {
    rows?: Array<{
      revenue_growth: number;
      values: Array<{ wacc: number; value_per_share: number }>;
    }>;
    trace?: Record<string, unknown>;
  };
  trace: {
    method?: string;
    input_source?: string;
    fact_ids?: Record<string, number | null>;
    periods?: Record<string, string | null>;
    bootstrap_notice?: string;
    [key: string]: unknown;
  };
};

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${BACKEND_URL}${path}`, {
      cache: 'no-store',
    });
    if (!response.ok) return fallback;
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

async function postJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${BACKEND_URL}${path}`, {
      method: 'POST',
      cache: 'no-store',
    });
    if (!response.ok) return fallback;
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

export async function getResearchDashboard() {
  const [companies, portfolio, workflowsPayload, settings] = await Promise.all([
    getJson<ResearchCompany[]>('/api/companies', []),
    getJson<ResearchPortfolioSummary>('/api/portfolio/summary', {
      total_value: 0,
      equity_value: 0,
      cash: {},
      top_1_weight: 0,
      top_5_weight: 0,
      alerts: [],
    }),
    getJson<{ workflows: ResearchWorkflow[] }>('/api/workflows', { workflows: [] }),
    getJson<ResearchSettings>('/api/settings', {
      app_env: 'unknown',
      maf_version: 'not loaded',
      budget: {
        daily_cost_eur: 0,
        monthly_cost_eur: 0,
        daily_cap_eur: 0,
        monthly_cap_eur: 0,
      },
      connectors: {},
    }),
  ]);

  return {
    companies,
    portfolio,
    workflows: workflowsPayload.workflows,
    settings,
  };
}

export async function getResearchCompanyDetail(ticker: string) {
  const normalizedTicker = ticker.toUpperCase();
  const emptyValuation: ResearchValuation = {
    ticker: normalizedTicker,
    model_type: 'unknown',
    current_price: 0,
    bear_value: 0,
    base_value: 0,
    bull_value: 0,
    expected_value: 0,
    margin_of_safety: 0,
    reverse_dcf: {},
    sensitivity: { rows: [] },
    trace: {},
  };

  const [company, valuation, facts] = await Promise.all([
    getJson<ResearchCompany | null>(`/api/companies/${encodeURIComponent(normalizedTicker)}`, null),
    getJson<ResearchValuation>(`/api/valuation/${encodeURIComponent(normalizedTicker)}`, emptyValuation),
    getJson<ResearchFact[]>(`/api/companies/${encodeURIComponent(normalizedTicker)}/facts?limit=80`, []),
  ]);

  return {
    company,
    valuation,
    facts,
  };
}

export async function refreshCompanyFinancials(ticker: string) {
  const normalizedTicker = ticker.toUpperCase();
  await postJson(`/api/companies/${encodeURIComponent(normalizedTicker)}/refresh/fmp`, {
    status: 'not_configured',
    ticker: normalizedTicker,
  });
  revalidatePath('/research');
  revalidatePath(`/research/${normalizedTicker}`);
}

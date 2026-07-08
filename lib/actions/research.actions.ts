'use server';

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

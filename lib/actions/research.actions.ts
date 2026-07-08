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

export type ResearchThesis = {
  id: number;
  company_id: number;
  version: number;
  status: string;
  thesis_markdown: string;
  executive_summary: string;
  rating: string;
  current_price: string;
  bear_value: string;
  base_value: string;
  bull_value: string;
  expected_value: string;
  margin_of_safety: string;
  data_confidence_score: number;
  source_coverage_score: number;
  red_team_score: number;
  valuation_risk_score: number;
  created_at: string;
};

export type ResearchSourceDocument = {
  id: number;
  ticker: string | null;
  title: string;
  source_type: string;
  source_url: string | null;
  published_at: string | null;
};

export type ResearchSourceAudit = {
  id: number;
  thesis_version_id: number | null;
  passed: boolean;
  source_coverage_score: number;
  unsupported_claims: string[];
  weak_claims: string[];
  data_conflicts: string[];
  required_fixes: string[];
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

async function postJson<T>(path: string, fallback: T, body?: unknown): Promise<T> {
  try {
    const response = await fetch(`${BACKEND_URL}${path}`, {
      method: 'POST',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
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

  const [company, valuation, facts, thesis] = await Promise.all([
    getJson<ResearchCompany | null>(`/api/companies/${encodeURIComponent(normalizedTicker)}`, null),
    getJson<ResearchValuation>(`/api/valuation/${encodeURIComponent(normalizedTicker)}`, emptyValuation),
    getJson<ResearchFact[]>(`/api/companies/${encodeURIComponent(normalizedTicker)}/facts?limit=80`, []),
    getJson<ResearchThesis | null>(`/api/thesis/${encodeURIComponent(normalizedTicker)}/latest`, null),
  ]);

  return {
    company,
    valuation,
    facts,
    thesis,
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

export async function generateResearchThesis(ticker: string) {
  const normalizedTicker = ticker.toUpperCase();
  await postJson(
    '/api/thesis/generate',
    null,
    {
      ticker: normalizedTicker,
      force_new_version: true,
    },
  );
  revalidatePath('/research');
  revalidatePath(`/research/${normalizedTicker}`);
}

export async function getResearchSources() {
  const [documents, audits] = await Promise.all([
    getJson<ResearchSourceDocument[]>('/api/sources/documents', []),
    getJson<ResearchSourceAudit[]>('/api/sources/audits', []),
  ]);

  return {
    documents,
    audits,
  };
}

export async function importResearchSource(formData: FormData) {
  const ticker = String(formData.get('ticker') ?? '').trim().toUpperCase();
  const title = String(formData.get('title') ?? '').trim();
  const text = String(formData.get('text') ?? '').trim();
  const sourceUrl = String(formData.get('source_url') ?? '').trim();
  const period = String(formData.get('period') ?? '').trim() || 'unknown';

  if (!ticker || !title || text.length < 20) return;

  await postJson('/api/sources/quartr/import-text', null, {
    ticker,
    title,
    text,
    source_url: sourceUrl || null,
    period,
  });

  revalidatePath('/research/sources');
}

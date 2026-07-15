'use server';

import { revalidatePath } from 'next/cache';
import { researchIdentityHeaders } from '@/lib/auth/research-identity';
import { AppError, ExternalAPIError, ValidationError } from '@/lib/types/errors';

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

export type ResearchCalculatedMetric = {
  id: number | null;
  company_id: number | null;
  metric: string;
  value: string | null;
  unit: string;
  period: string;
  fiscal_year: number | null;
  fiscal_quarter: string | null;
  status: string;
  definition_version: string;
  formula: string;
  numerator: string | null;
  denominator: string | null;
  source_fact_ids: number[];
  calculation_trace: Record<string, unknown>;
  confidence: string;
};

export type ResearchPeerComparison = {
  ticker: string;
  basis: string;
  selection_trace?: Record<string, unknown>;
  peer_count: number;
  metrics: string[];
  benchmarks: Record<
    string,
    {
      peer_median: string | null;
      peer_average: string | null;
      peer_sample_size: number;
      target_value: string | null;
      target_vs_peer_median: string | null;
    }
  >;
  companies: Array<{
    ticker: string;
    name: string;
    sector: string;
    industry: string;
    is_target: boolean;
    metrics: Record<
      string,
      {
        value: string | null;
        status: string;
        unit: string;
        period: string;
        confidence: string;
        source_fact_ids: number[];
      }
    >;
  }>;
};

export type ResearchValuation = {
  ticker: string;
  model_type: string;
  status?: string;
  publishable?: boolean;
  current_price: number | null;
  bear_value: number | null;
  base_value: number | null;
  bull_value: number | null;
  expected_value: number | null;
  margin_of_safety: number | null;
  missing_inputs?: string[];
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
  moat?: Record<string, unknown>;
  trace: {
    method?: string;
    engine?: string;
    input_source?: string;
    fact_ids?: Record<string, number | null>;
    periods?: Record<string, string | null>;
    bootstrap_notice?: string;
    missing_inputs?: string[];
    publishable?: boolean;
    status?: string;
    notice?: string;
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
  source_tier: string;
  source_url: string | null;
  storage_uri?: string | null;
  checksum?: string | null;
  metadata?: Record<string, unknown>;
  published_at: string | null;
  chunks?: ResearchSourceChunk[];
};

export type ResearchSourceChunk = {
  id: number;
  document_id: number;
  chunk_index: number;
  text: string;
  token_count: number;
  metadata?: Record<string, unknown>;
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

export type ResearchClaimEvidence = {
  id: number;
  claim_id: number;
  document_id: number | null;
  document_chunk_id: number | null;
  evidence_type: string;
  summary: string;
  source_url: string | null;
  source_tier: string;
  confidence: string;
  created_at: string;
};

export type ResearchClaim = {
  id: number;
  company_id: number | null;
  thesis_version_id: number | null;
  statement: string;
  claim_type: string;
  status: string;
  confidence: string;
  materiality_score: number;
  source_quality: string;
  evidence: ResearchClaimEvidence[];
  created_at: string;
};

export type ResearchThesisSection = {
  id: number;
  thesis_version_id: number;
  company_id: number;
  section_key: string;
  title: string;
  body: string;
  status: string;
  order_index: number;
  confidence: string;
  updated_at: string;
};

export type ResearchThesisChange = {
  id: number;
  company_id: number | null;
  from_version_id: number | null;
  to_version_id: number | null;
  change_type: string;
  impact_direction: 'positive' | 'negative' | 'neutral' | 'mixed' | string;
  materiality_score: number;
  summary: string;
  affected_claim_ids: number[];
  affected_metrics: string[];
  requires_review: boolean;
  created_at: string;
  updated_at: string;
};

export type ResearchMemoryItem = {
  id: number;
  company_id: number | null;
  research_session_id: number | null;
  scope: string;
  memory_type: string;
  importance: number;
  content: string;
  status: string;
  source_type: string;
  created_at: string;
};

export type ResearchChatResponse = {
  answer: string;
  sections: Array<{
    key: 'facts' | 'calculations' | 'user_hypotheses' | 'inferences' | 'contradictions' | 'insufficient_data' | 'conclusion';
    body: string;
    citations: string[];
  }>;
  sources: Array<{
    type: string;
    id: number | string | null;
    title: string;
    [key: string]: unknown;
  }>;
  blocked: boolean;
  proposed_actions: string[];
  evidence_suggestions: ResearchEvidenceSuggestion[];
  prompt_version?: string | null;
  model?: string | null;
};

export type ResearchEvidenceSuggestion = {
  id: number;
  company_id: number | null;
  document_id: number | null;
  document_chunk_id: number | null;
  suggested_claim_id: number | null;
  suggestion_type: string;
  statement: string;
  relation: string;
  rationale: string;
  quote: string | null;
  confidence: string;
  status: string;
  prompt_version: string;
  metadata_: Record<string, unknown>;
  created_at: string;
};

export type ResearchReview = {
  id: number;
  company_id: number | null;
  review_type: string;
  status: string;
  priority: string;
  title: string;
  summary: string;
  thesis_change_id: number | null;
  claim_id: number | null;
  news_event_id: number | null;
  created_at: string;
};

export type ResearchAlert = {
  id: number;
  company_id: number | null;
  review_id: number | null;
  severity: string;
  status: string;
  alert_type: string;
  title: string;
  message: string;
  channels: string[];
  snoozed_until: string | null;
  created_at: string;
};

export type ResearchThesisGraph = {
  ticker: string;
  thesis_version_id: number;
  nodes: Array<{
    id: number;
    node_key: string;
    node_type: string;
    label: string;
    description: string;
    status: string;
    confidence: string;
    materiality_score: number;
    claim_ids: number[];
    invalidation_conditions: string[];
  }>;
  edges: Array<{
    id: number;
    from_node_id: number;
    to_node_id: number;
    edge_type: string;
    strength: string;
  }>;
};

export type ResearchPeerAnalysis = {
  ticker: string;
  status: string;
  selection: {
    basis: string;
    trace: Record<string, unknown>;
    peers: string[];
  };
  advantages: Array<Record<string, unknown>>;
  disadvantages: Array<Record<string, unknown>>;
  insufficient_data: string[];
  methodology: string;
};

export type ResearchMoat = {
  ticker: string;
  status: string;
  methodology: string;
  moats: Array<{
    type: string;
    strength: number;
    trend: string;
    persistence: string;
    confidence: number;
    status: string;
    supporting_claim_ids: number[];
    contradicting_claim_ids: number[];
  }>;
};

export type ResearchRedTeam = {
  id: number;
  score: number;
  status: string;
  strongest_bear_case: string;
  findings: Array<{
    severity: string;
    type: string;
    message: string;
    trace: Record<string, unknown>;
  }>;
  broken_assumptions: string[];
  missing_risks: string[];
  falsification_tests: string[];
  created_at: string;
};

export type ResearchLongTermForecast = {
  year: number;
  revenue: number | null;
  gross_profit: number | null;
  operating_income: number | null;
  ebitda: number | null;
  net_income: number | null;
  operating_cash_flow: number | null;
  capital_expenditure: number | null;
  free_cash_flow: number | null;
  working_capital: number | null;
  working_capital_absorption: number | null;
  net_debt: number | null;
  shares_diluted: number | null;
  fcf_per_share: number | null;
  fcf_margin: number | null;
  roic: number | null;
  scenario: string;
  wacc: number;
  evidence: Record<string, { source_fact_ids: number[]; calculation: string }>;
};

export type ResearchLongTermScenario = {
  probability: number;
  assumptions: Record<string, { value: number | null; unit: string; source_type: string; basis: string; source_fact_ids: number[] }>;
  drivers: string[];
  forecast: ResearchLongTermForecast[];
  year_5: ResearchLongTermForecast | null;
  terminal_year: ResearchLongTermForecast | null;
  revenue_bridge: { status: string; items?: Array<{ label: string; value: number | null; source_fact_ids: number[]; note?: string }>; unavailable_drivers?: string[] };
  fcf_bridge: { status: string; items?: Array<{ label: string; value: number | null; source_fact_ids: number[] }>; unavailable_drivers?: string[] };
  valuation: { value_per_share: number; enterprise_value: number; equity_value: number } | null;
};

export type ResearchLongTermModel = {
  ticker: string;
  company: string;
  currency: string;
  status: string;
  publishable: boolean;
  model: string;
  model_version: string;
  framework: {
    key: string;
    label: string;
    primary_question: string;
    market_opportunity_mode: string;
    revenue_drivers: string[];
    kpis: string[];
    unit_economics: string[];
    segment_model: string[];
    binding_constraints: string[];
    active_modules: string[];
  };
  operating_model: {
    revenue_drivers: string[];
    kpis: string[];
    unit_economics: string[];
    segment_model: string[];
    binding_constraints: string[];
    active_modules: string[];
  };
  horizon_years: number;
  as_of_period: string | null;
  current_price: number | null;
  missing_inputs: string[];
  missing_mandatory_drivers: string[];
  driver_model: Array<{
    key: string;
    driver_type: 'revenue_driver' | 'kpi';
    required: boolean;
    status: 'sourced' | 'missing';
    value: number | null;
    unit: string;
    confidence: number;
    source_fact_ids: number[];
  }>;
  persistence: {
    model_version_id: number | null;
    version: number | null;
    input_fingerprint: string | null;
    status: string;
  };
  historical_review: { years_covered: number; first_year: number | null; last_year: number | null; rows: Array<Record<string, unknown>> };
  current_snapshot: { period: string | null; fiscal_year: number | null; metrics: Record<string, { value: number | null; source_fact_ids: number[]; status: string }> };
  assumptions: Record<string, { value: number | null; unit: string; source_type: string; basis: string; source_fact_ids: number[]; confidence: number }>;
  scenarios: Record<string, ResearchLongTermScenario>;
  reverse_dcf: { status: string; required_revenue_growth?: number; base_revenue_growth?: number; growth_gap_vs_base?: number; market_price?: number | null; missing_inputs?: string[] };
  market_opportunity: {
    status: string;
    mode: string;
    primary_question: string;
    top_down: {
      status: string;
      market_type: string | null;
      tam: { value: number | null; unit: string; source_fact_ids: number[] };
      sam: { value: number | null; unit: string; source_fact_ids: number[] };
      som: { value: number | null; unit: string; source_fact_ids: number[] };
      future_market: { value: number | null; source_fact_ids: number[] };
      current_market_share: number | null;
      missing_inputs: string[];
    };
    bottom_up: { status: string; value: number | null; formulas: Array<{ label: string; value: number | null; status: string; missing_inputs?: string[]; source_fact_ids: number[] }>; missing_inputs: string[] };
    implied_by_valuation: { status: string; conclusion: string; current_market_share: number | null; prior_market_share: number | null; base_future_market_share: number | null; valuation_implied_market_share: number | null; missing_inputs: string[]; source_fact_ids: number[] };
    market_share: { status: string; conclusion: string; confidence: string; current_market_share: number | null; prior_market_share: number | null; base_future_market_share: number | null; valuation_implied_market_share: number | null; source_fact_ids: number[]; missing_inputs: string[] };
    constraints: { status: string; binding_constraint: string | null; severity: string; conclusion: string; framework_constraints: string[] };
    verdict: { label: string; confidence: string; conclusion: string; base_revenue_to_binding_capacity?: number };
    missing_inputs: string[];
  };
  market_share: { status: string; conclusion: string; confidence: string; current_market_share?: number; prior_market_share?: number | null; implied_future_market_share?: number | null; missing_inputs?: string[] };
  management_capital_allocation: { status: string; metrics: Record<string, { value: number | null; unit: string; status: string; source_fact_ids: number[]; calculation?: string; note?: string }>; conclusion: string; missing_inputs: string[] };
  quality_of_growth: { status: string; quality: string; revenue_cagr: { value: number | null }; fcf_margin_change: { value: number | null }; share_count_cagr: { value: number | null }; unavailable_drivers: string[]; conclusion: string };
  owner_earnings: { status: string; value: number | null; formula: string; missing_inputs?: string[]; source_fact_ids: number[] };
  capex_analysis: { status: string; total_capex: number | null; maintenance_capex: number | null; growth_capex: number | null; missing_inputs?: string[]; maintenance_vs_growth?: string };
  timeline: Array<{ date: string | null; type: string; title: string; source: string; thesis_impact: string; source_url?: string | null }>;
  what_must_be_true: Array<{ id: string; condition: string; value: number | null; unit: string; source_fact_ids: number[]; status: string; comparison?: number | null }>;
  source_coverage: { coverage_percent: number; sourced_values: number; numeric_values: number; rule: string };
  limitations: string[];
};

export type ResearchDecisionJournalEntry = {
  id: number;
  thesis_version_id: number | null;
  model_version_id: number | null;
  decision_date: string;
  decision: string;
  rationale: string;
  what_must_be_true: string[];
  price: number | null;
  status: string;
  metadata: Record<string, unknown>;
};

export type ResearchExpectationReview = {
  id: number;
  model_version_id: number;
  forecast_id: number;
  actual_fact_id: number | null;
  fiscal_year: number;
  metric: string;
  expected_value: number;
  actual_value: number | null;
  variance: number | null;
  variance_percent: number | null;
  status: string;
  reviewed_at: string | null;
};

async function researchRequestHeaders(): Promise<Record<string, string>> {
  return researchIdentityHeaders();
}

async function researchApiError(response: Response, path: string): Promise<never> {
  let detail = `${response.status} ${response.statusText}`.trim();
  try {
    const payload = await response.json() as { detail?: string; message?: string };
    detail = payload.detail ?? payload.message ?? detail;
  } catch {
    // Keep the HTTP status when the backend did not return JSON.
  }
  throw new AppError(detail, 'RESEARCH_API_ERROR', response.status, { path });
}

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${BACKEND_URL}${path}`, {
      cache: 'no-store',
      headers: await researchRequestHeaders(),
    });
    if (response.status === 404) return fallback;
    if (!response.ok) return researchApiError(response, path);
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof AppError) throw error;
    throw new ExternalAPIError(`Research API request failed: ${path}`, 'research-api', error);
  }
}

async function postJson<T>(path: string, fallback: T, body?: unknown): Promise<T> {
  try {
    const authHeaders = await researchRequestHeaders();
    const response = await fetch(`${BACKEND_URL}${path}`, {
      method: 'POST',
      headers: body
        ? { ...authHeaders, 'Content-Type': 'application/json' }
        : authHeaders,
      body: body ? JSON.stringify(body) : undefined,
      cache: 'no-store',
    });
    if (!response.ok) return researchApiError(response, path);
    if (response.status === 204) return fallback;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof AppError) throw error;
    throw new ExternalAPIError(`Research API mutation failed: ${path}`, 'research-api', error);
  }
}

async function postForm<T>(path: string, fallback: T, body: FormData): Promise<T> {
  try {
    const response = await fetch(`${BACKEND_URL}${path}`, {
      method: 'POST',
      body,
      cache: 'no-store',
      headers: await researchRequestHeaders(),
    });
    if (!response.ok) return researchApiError(response, path);
    if (response.status === 204) return fallback;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof AppError) throw error;
    throw new ExternalAPIError(`Research API upload failed: ${path}`, 'research-api', error);
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

export async function ensureResearchCompany(ticker: string, name?: string) {
  const normalizedTicker = ticker.trim().toUpperCase();
  if (!/^[A-Z0-9.\-]{1,20}$/.test(normalizedTicker)) {
    throw new AppError('Invalid ticker', 'VALIDATION_ERROR', 400, { field: 'ticker' });
  }
  return postJson<ResearchCompany>('/api/companies/ensure', null as never, {
    ticker: normalizedTicker,
    name: name?.trim() || null,
  });
}

export async function getResearchCompanyDetail(ticker: string) {
  const normalizedTicker = ticker.toUpperCase();
  const emptyValuation: ResearchValuation = {
    ticker: normalizedTicker,
    model_type: 'unknown',
    status: 'insufficient_data',
    publishable: false,
    current_price: null,
    bear_value: null,
    base_value: null,
    bull_value: null,
    expected_value: null,
    margin_of_safety: null,
    missing_inputs: [],
    reverse_dcf: {},
    sensitivity: { rows: [] },
    moat: {},
    trace: { input_source: 'insufficient_data' },
  };

  const [
    company,
    valuation,
    facts,
    calculatedMetricsPayload,
    peerComparison,
    peerAnalysis,
    moat,
    thesis,
    claims,
    thesisSections,
    thesisChanges,
    thesisGraph,
    reviews,
    alerts,
    memoryItems,
    sourceDocuments,
    evidenceSuggestions,
    redTeam,
    longTermModel,
    decisionJournal,
    expectationReviews,
  ] = await Promise.all([
    getJson<ResearchCompany | null>(`/api/companies/${encodeURIComponent(normalizedTicker)}`, null),
    getJson<ResearchValuation>(`/api/valuation/${encodeURIComponent(normalizedTicker)}`, emptyValuation),
    getJson<ResearchFact[]>(`/api/companies/${encodeURIComponent(normalizedTicker)}/facts?limit=80`, []),
    getJson<{ metrics: ResearchCalculatedMetric[] }>(`/api/companies/${encodeURIComponent(normalizedTicker)}/metrics/calculated`, { metrics: [] }),
    getJson<ResearchPeerComparison | null>(`/api/companies/${encodeURIComponent(normalizedTicker)}/peers/comparison`, null),
    getJson<ResearchPeerAnalysis | null>(`/api/companies/${encodeURIComponent(normalizedTicker)}/peers/analysis`, null),
    getJson<ResearchMoat | null>(`/api/companies/${encodeURIComponent(normalizedTicker)}/moat`, null),
    getJson<ResearchThesis | null>(`/api/thesis/${encodeURIComponent(normalizedTicker)}/latest`, null),
    getJson<ResearchClaim[]>(`/api/memory/claims?ticker=${encodeURIComponent(normalizedTicker)}&limit=20`, []),
    getJson<ResearchThesisSection[]>(`/api/memory/thesis/${encodeURIComponent(normalizedTicker)}/sections`, []),
    getJson<ResearchThesisChange[]>(`/api/memory/thesis/${encodeURIComponent(normalizedTicker)}/changes`, []),
    getJson<ResearchThesisGraph | null>(`/api/thesis/${encodeURIComponent(normalizedTicker)}/graph`, null),
    getJson<ResearchReview[]>(`/api/reviews?ticker=${encodeURIComponent(normalizedTicker)}&status=open`, []),
    getJson<ResearchAlert[]>(`/api/alerts?ticker=${encodeURIComponent(normalizedTicker)}`, []),
    getJson<ResearchMemoryItem[]>(`/api/memory/memory-items?ticker=${encodeURIComponent(normalizedTicker)}&scope=company&limit=20`, []),
    getJson<ResearchSourceDocument[]>(`/api/sources/documents?ticker=${encodeURIComponent(normalizedTicker)}&include_chunks=true&chunk_text_limit=1800`, []),
    getJson<ResearchEvidenceSuggestion[]>(`/api/sources/evidence-suggestions?ticker=${encodeURIComponent(normalizedTicker)}&status=pending`, []),
    getJson<ResearchRedTeam | null>(`/api/companies/${encodeURIComponent(normalizedTicker)}/red-team/latest`, null),
    getJson<ResearchLongTermModel | null>(`/api/companies/${encodeURIComponent(normalizedTicker)}/long-term-model?horizon=5`, null),
    getJson<ResearchDecisionJournalEntry[]>(`/api/companies/${encodeURIComponent(normalizedTicker)}/decision-journal`, []),
    getJson<ResearchExpectationReview[]>(`/api/companies/${encodeURIComponent(normalizedTicker)}/expectation-reality`, []),
  ]);

  return {
    company,
    valuation,
    facts,
    calculatedMetrics: calculatedMetricsPayload.metrics,
    peerComparison,
    peerAnalysis,
    moat,
    thesis,
    claims,
    thesisSections,
    thesisChanges,
    thesisGraph,
    reviews,
    alerts,
    memoryItems,
    sourceDocuments,
    evidenceSuggestions,
    redTeam,
    longTermModel,
    decisionJournal,
    expectationReviews,
  };
}

export async function createResearchDecision(ticker: string, formData: FormData) {
  const normalizedTicker = ticker.toUpperCase();
  const decision = String(formData.get('decision') ?? '').trim();
  const rationale = String(formData.get('rationale') ?? '').trim();
  const whatMustBeTrue = String(formData.get('what_must_be_true') ?? '')
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (!['buy', 'hold', 'trim', 'sell', 'watch', 'avoid'].includes(decision)) {
    throw new ValidationError('Selecciona una decisión válida', 'decision');
  }
  if (rationale.length < 5) {
    throw new ValidationError('Explica la decisión con al menos 5 caracteres', 'rationale');
  }
  await postJson(
    `/api/companies/${encodeURIComponent(normalizedTicker)}/decision-journal`,
    null,
    { decision, rationale, what_must_be_true: whatMustBeTrue },
  );
  revalidatePath(`/research/${normalizedTicker}`);
}

export async function reviewResearchExpectations(ticker: string) {
  const normalizedTicker = ticker.toUpperCase();
  await postJson(
    `/api/companies/${encodeURIComponent(normalizedTicker)}/expectation-reality/review`,
    [],
  );
  revalidatePath(`/research/${normalizedTicker}`);
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

export async function createResearchClaim(ticker: string, formData: FormData) {
  const normalizedTicker = ticker.toUpperCase();
  const statement = String(formData.get('statement') ?? '').trim();
  const claimType = String(formData.get('claim_type') ?? 'thesis').trim() || 'thesis';
  const materiality = Number(formData.get('materiality_score') ?? 5);

  if (statement.length < 5) throw new ValidationError('La afirmación debe tener al menos 5 caracteres', 'statement');

  await postJson('/api/memory/claims', null, {
    ticker: normalizedTicker,
    statement,
    claim_type: claimType,
    materiality_score: Number.isFinite(materiality) ? Math.max(0, Math.min(10, materiality)) : 5,
    created_by: 'user',
  });

  revalidatePath('/research');
  revalidatePath(`/research/${normalizedTicker}`);
}

export async function addResearchClaimEvidence(ticker: string, claimId: number, formData: FormData) {
  const normalizedTicker = ticker.toUpperCase();
  const summary = String(formData.get('summary') ?? '').trim();
  const evidenceType = String(formData.get('evidence_type') ?? 'supports').trim();
  const sourceUrl = String(formData.get('source_url') ?? '').trim();
  const sourceRef = String(formData.get('source_ref') ?? '').trim();
  const [sourceRefType, sourceRefId] = sourceRef.split(':');
  const parsedSourceRefId = Number(sourceRefId);
  const documentId = sourceRefType === 'document' ? parsedSourceRefId : Number(formData.get('document_id') ?? 0);
  const documentChunkId = sourceRefType === 'chunk' ? parsedSourceRefId : Number(formData.get('document_chunk_id') ?? 0);

  if (summary.length < 3) throw new ValidationError('El resumen de evidencia debe tener al menos 3 caracteres', 'summary');

  await postJson(`/api/memory/claims/${claimId}/evidence`, null, {
    evidence_type: evidenceType === 'contradicts' ? 'contradicts' : 'supports',
    summary,
    source_url: sourceUrl || null,
    document_id: Number.isFinite(documentId) && documentId > 0 ? documentId : null,
    document_chunk_id: Number.isFinite(documentChunkId) && documentChunkId > 0 ? documentChunkId : null,
  });

  revalidatePath('/research');
  revalidatePath(`/research/${normalizedTicker}`);
}

export async function createResearchClaimFromChunk(ticker: string, chunkId: number, formData: FormData) {
  const normalizedTicker = ticker.toUpperCase();
  const statement = String(formData.get('statement') ?? '').trim();
  const summary = String(formData.get('summary') ?? statement).trim();
  const evidenceType = String(formData.get('evidence_type') ?? 'supports').trim();
  const sourceUrl = String(formData.get('source_url') ?? '').trim();
  const materiality = Number(formData.get('materiality_score') ?? 5);

  if (statement.length < 5) throw new ValidationError('La afirmación debe tener al menos 5 caracteres', 'statement');
  if (summary.length < 3) throw new ValidationError('El resumen de evidencia debe tener al menos 3 caracteres', 'summary');
  if (!Number.isFinite(chunkId) || chunkId <= 0) throw new ValidationError('El fragmento de origen no es válido', 'chunkId');

  const claim = await postJson<ResearchClaim | null>('/api/memory/claims', null, {
    ticker: normalizedTicker,
    statement,
    claim_type: 'source_extracted',
    materiality_score: Number.isFinite(materiality) ? Math.max(0, Math.min(10, materiality)) : 5,
    source_quality: 'backend_classified',
    created_by: 'user',
  });

  if (!claim?.id) throw new AppError('No se pudo crear la afirmación', 'CLAIM_CREATION_FAILED', 502);

  await postJson(`/api/memory/claims/${claim.id}/evidence`, null, {
    evidence_type: evidenceType === 'contradicts' ? 'contradicts' : 'supports',
    summary,
    source_url: sourceUrl || null,
    document_chunk_id: chunkId,
  });

  revalidatePath('/research');
  revalidatePath(`/research/${normalizedTicker}`);
}

export async function addResearchChunkEvidence(ticker: string, chunkId: number, formData: FormData) {
  const normalizedTicker = ticker.toUpperCase();
  const claimId = Number(formData.get('claim_id') ?? 0);
  const summary = String(formData.get('summary') ?? '').trim();
  const evidenceType = String(formData.get('evidence_type') ?? 'supports').trim();
  const sourceUrl = String(formData.get('source_url') ?? '').trim();

  if (!Number.isFinite(claimId) || claimId <= 0) throw new ValidationError('La afirmación seleccionada no es válida', 'claim_id');
  if (summary.length < 3) throw new ValidationError('El resumen de evidencia debe tener al menos 3 caracteres', 'summary');
  if (!Number.isFinite(chunkId) || chunkId <= 0) throw new ValidationError('El fragmento de origen no es válido', 'chunkId');

  await postJson(`/api/memory/claims/${claimId}/evidence`, null, {
    evidence_type: evidenceType === 'contradicts' ? 'contradicts' : 'supports',
    summary,
    source_url: sourceUrl || null,
    document_chunk_id: chunkId,
  });

  revalidatePath('/research');
  revalidatePath(`/research/${normalizedTicker}`);
}

export async function createResearchThesisChange(ticker: string, formData: FormData) {
  const normalizedTicker = ticker.toUpperCase();
  const summary = String(formData.get('summary') ?? '').trim();
  const changeType = String(formData.get('change_type') ?? 'manual').trim() || 'manual';
  const impactDirection = String(formData.get('impact_direction') ?? 'neutral').trim() || 'neutral';
  const materiality = Number(formData.get('materiality_score') ?? 5);
  const affectedMetrics = String(formData.get('affected_metrics') ?? '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

  if (summary.length < 5) throw new ValidationError('El cambio debe describirse con al menos 5 caracteres', 'summary');

  await postJson('/api/memory/thesis/changes', null, {
    ticker: normalizedTicker,
    change_type: changeType,
    impact_direction: ['positive', 'negative', 'neutral', 'mixed'].includes(impactDirection)
      ? impactDirection
      : 'neutral',
    materiality_score: Number.isFinite(materiality) ? Math.max(0, Math.min(10, materiality)) : 5,
    summary,
    affected_metrics: affectedMetrics,
    requires_review: true,
  });

  revalidatePath('/research');
  revalidatePath(`/research/${normalizedTicker}`);
}

export async function createResearchMemoryItem(ticker: string, formData: FormData) {
  const normalizedTicker = ticker.toUpperCase();
  const content = String(formData.get('content') ?? '').trim();
  const memoryType = String(formData.get('memory_type') ?? 'note').trim() || 'note';
  const importance = Number(formData.get('importance') ?? 5);

  if (content.length < 3) throw new ValidationError('La nota debe tener al menos 3 caracteres', 'content');

  await postJson('/api/memory/memory-items', null, {
    ticker: normalizedTicker,
    scope: 'company',
    memory_type: memoryType,
    importance: Number.isFinite(importance) ? Math.max(0, Math.min(10, importance)) : 5,
    content,
    source_type: 'user',
  });

  revalidatePath('/research');
  revalidatePath(`/research/${normalizedTicker}`);
}

export async function askResearchCompanyChat(ticker: string, question: string): Promise<ResearchChatResponse | null> {
  const normalizedTicker = ticker.toUpperCase();
  const trimmedQuestion = question.trim();
  if (trimmedQuestion.length < 3) return null;

  return postJson<ResearchChatResponse>(
    '/api/chat',
    {
      answer: 'No response available from the research engine.',
      sections: [],
      sources: [],
      blocked: true,
      proposed_actions: ['Check backend status'],
      evidence_suggestions: [],
    },
    {
      ticker: normalizedTicker,
      scope: 'company',
      question: trimmedQuestion,
    },
  );
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

  if (!ticker) throw new ValidationError('El ticker es obligatorio', 'ticker');
  if (!title) throw new ValidationError('El título es obligatorio', 'title');
  if (text.length < 20) throw new ValidationError('El documento debe tener al menos 20 caracteres', 'text');

  await postJson('/api/sources/quartr/import-text', null, {
    ticker,
    title,
    text,
    source_url: sourceUrl || null,
    period,
  });

  revalidatePath('/research/sources');
}

export async function importResearchDocumentFile(formData: FormData) {
  const ticker = String(formData.get('ticker') ?? '').trim().toUpperCase();
  const title = String(formData.get('title') ?? '').trim();
  const file = formData.get('file');

  if (!ticker) throw new ValidationError('El ticker es obligatorio', 'ticker');
  if (!title) throw new ValidationError('El título es obligatorio', 'title');
  if (!(file instanceof File) || file.size === 0) throw new ValidationError('Selecciona un archivo no vacío', 'file');

  await postForm('/api/sources/documents/ingest-file', null, formData);
  revalidatePath('/research/sources');
  revalidatePath(`/research/${ticker}`);
}

export async function importResearchDocumentUrl(formData: FormData) {
  const ticker = String(formData.get('ticker') ?? '').trim().toUpperCase();
  const title = String(formData.get('title') ?? '').trim();
  const url = String(formData.get('url') ?? '').trim();
  const sourceType = String(formData.get('source_type') ?? 'url').trim() || 'url';

  if (!ticker) throw new ValidationError('El ticker es obligatorio', 'ticker');
  if (!title) throw new ValidationError('El título es obligatorio', 'title');
  if (!url) throw new ValidationError('La URL es obligatoria', 'url');

  await postJson('/api/sources/documents/ingest-url', null, {
    ticker,
    title,
    url,
    source_type: sourceType,
  });
  revalidatePath('/research/sources');
  revalidatePath(`/research/${ticker}`);
}

export type ResearchNewsEvent = {
  id: number;
  ticker: string | null;
  date: string;
  title: string;
  source: string;
  url: string | null;
  event_type: string;
  materiality_score: number;
  impact_direction: string;
  requires_update: boolean;
  source_tier?: string;
  source_trust_score?: number;
  portfolio_weight?: number;
  materiality_reasons?: string[];
  source_policy?: string;
  model_route?: string;
};

export type ResearchWorkflowRun = {
  status: string;
  workflow: string;
  ticker: string | null;
  message: string;
  steps: string[];
  estimated_minutes: number;
  result?: unknown;
};

export type ResearchThesisVersion = {
  id: number;
  version: number;
  status: string;
  rating: string;
  executive_summary: string;
  source_coverage_score: number;
  data_confidence_score: number;
  created_at: string;
};

export async function getResearchNews(): Promise<ResearchNewsEvent[]> {
  return getJson<ResearchNewsEvent[]>('/api/news', []);
}

export async function analyzeManualNews(
  formData: FormData,
): Promise<{
  ticker?: string | null;
  event_type: string;
  materiality_score: number;
  impact_direction: string;
  summary: string;
  source_tier?: string;
  portfolio_weight?: number;
  materiality_reasons?: string[];
}> {
  const text = String(formData.get('text') ?? '').trim();
  const source = String(formData.get('source') ?? 'manual').trim();
  const url = String(formData.get('url') ?? '').trim();
  if (!text || text.length < 20) throw new ValidationError('La noticia debe tener al menos 20 caracteres', 'text');

  const result = await postJson(
    '/api/news/manual',
    { ticker: null, event_type: 'unknown', materiality_score: 0, impact_direction: 'neutral', summary: '' },
    { text, source, url: url || null },
  );

  revalidatePath('/research');
  revalidatePath('/research/news');
  if (result.ticker) revalidatePath(`/research/${result.ticker}`);

  return result;
}

export async function ingestResearchNewsFeed(
  formData: FormData,
): Promise<{ status: string; received: number; created: number; skipped_duplicates: number; requires_update: number }> {
  const rawItems = String(formData.get('items') ?? '').trim();
  const source = String(formData.get('source') ?? 'manual_feed').trim() || 'manual_feed';
  if (!rawItems) throw new ValidationError('Introduce al menos una noticia en JSON', 'items');

  try {
    const parsed = JSON.parse(rawItems) as unknown;
    const items = Array.isArray(parsed) ? parsed : [parsed];
    const result = await postJson(
      '/api/news/ingest',
      { status: 'error', received: 0, created: 0, skipped_duplicates: 0, requires_update: 0 },
      { source, items },
    );

    revalidatePath('/research');
    revalidatePath('/research/news');
    return result;
  } catch (error) {
    if (error instanceof AppError) throw error;
    throw new ValidationError('El feed no contiene JSON válido', 'items');
  }
}

export async function refreshCompanyFinancialsSEC(ticker: string) {
  const normalizedTicker = ticker.toUpperCase();
  await postJson(`/api/companies/${encodeURIComponent(normalizedTicker)}/refresh/sec`, {
    status: 'not_configured',
    ticker: normalizedTicker,
  });
  revalidatePath('/research');
  revalidatePath(`/research/${normalizedTicker}`);
}

export async function runResearchWorkflow(name: string, ticker?: string): Promise<ResearchWorkflowRun> {
  const result = await postJson<ResearchWorkflowRun>(
    `/api/workflows/${encodeURIComponent(name)}/run`,
    { status: 'error', workflow: name, ticker: ticker ?? null, message: 'Backend unavailable', steps: [], estimated_minutes: 0 },
    { ticker: ticker ?? null, params: {} },
  );
  revalidatePath('/research');
  if (ticker) revalidatePath(`/research/${ticker.toUpperCase()}`);
  return result;
}

export async function getThesisHistory(ticker: string): Promise<ResearchThesisVersion[]> {
  return getJson<ResearchThesisVersion[]>(`/api/thesis/${encodeURIComponent(ticker.toUpperCase())}/versions`, []);
}

export async function actionResearchEvidenceSuggestion(
  ticker: string,
  suggestionId: number,
  action: 'accept' | 'reject',
  claimId?: number,
) {
  await postJson(
    `/api/sources/evidence-suggestions/${suggestionId}/action`,
    null,
    {
      action,
      claim_id: claimId ?? null,
    },
  );
  revalidatePath(`/research/${ticker.toUpperCase()}`);
}

export async function runResearchRedTeam(ticker: string) {
  const normalizedTicker = ticker.toUpperCase();
  await postJson(
    `/api/companies/${encodeURIComponent(normalizedTicker)}/red-team`,
    null,
  );
  revalidatePath(`/research/${normalizedTicker}`);
}

export async function runResearchEarnings(ticker: string, formData: FormData) {
  const normalizedTicker = ticker.toUpperCase();
  const fiscalYear = Number(formData.get('fiscal_year'));
  const fiscalQuarter = String(formData.get('fiscal_quarter') ?? 'FY');
  const documentIds = String(formData.get('document_ids') ?? '')
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isFinite(value) && value > 0);
  if (!Number.isInteger(fiscalYear)) throw new ValidationError('El ejercicio fiscal no es válido', 'fiscal_year');
  await postJson(
    `/api/earnings/${encodeURIComponent(normalizedTicker)}/run`,
    null,
    {
      fiscal_year: fiscalYear,
      fiscal_quarter: ['Q1', 'Q2', 'Q3', 'Q4', 'FY'].includes(fiscalQuarter)
        ? fiscalQuarter
        : 'FY',
      document_ids: documentIds,
      force_new_thesis: false,
    },
  );
  revalidatePath(`/research/${normalizedTicker}`);
}

export async function actionResearchAlert(
  ticker: string,
  alertId: number,
  action: 'acknowledge' | 'resolve' | 'reopen',
) {
  await postJson(`/api/alerts/${alertId}/action`, null, {
    action,
    actor: 'user',
  });
  revalidatePath(`/research/${ticker.toUpperCase()}`);
}

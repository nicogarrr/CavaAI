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
  sources: Array<{
    type: string;
    id: number | string | null;
    title: string;
    [key: string]: unknown;
  }>;
  blocked: boolean;
  proposed_actions: string[];
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

async function postForm<T>(path: string, fallback: T, body: FormData): Promise<T> {
  try {
    const response = await fetch(`${BACKEND_URL}${path}`, {
      method: 'POST',
      body,
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

  const [company, valuation, facts, calculatedMetricsPayload, thesis, claims, thesisSections, thesisChanges, memoryItems, sourceDocuments] = await Promise.all([
    getJson<ResearchCompany | null>(`/api/companies/${encodeURIComponent(normalizedTicker)}`, null),
    getJson<ResearchValuation>(`/api/valuation/${encodeURIComponent(normalizedTicker)}`, emptyValuation),
    getJson<ResearchFact[]>(`/api/companies/${encodeURIComponent(normalizedTicker)}/facts?limit=80`, []),
    getJson<{ metrics: ResearchCalculatedMetric[] }>(`/api/companies/${encodeURIComponent(normalizedTicker)}/metrics/calculated`, { metrics: [] }),
    getJson<ResearchThesis | null>(`/api/thesis/${encodeURIComponent(normalizedTicker)}/latest`, null),
    getJson<ResearchClaim[]>(`/api/memory/claims?ticker=${encodeURIComponent(normalizedTicker)}&limit=20`, []),
    getJson<ResearchThesisSection[]>(`/api/memory/thesis/${encodeURIComponent(normalizedTicker)}/sections`, []),
    getJson<ResearchThesisChange[]>(`/api/memory/thesis/${encodeURIComponent(normalizedTicker)}/changes`, []),
    getJson<ResearchMemoryItem[]>(`/api/memory/memory-items?ticker=${encodeURIComponent(normalizedTicker)}&scope=company&limit=20`, []),
    getJson<ResearchSourceDocument[]>(`/api/sources/documents?ticker=${encodeURIComponent(normalizedTicker)}&include_chunks=true&chunk_text_limit=1800`, []),
  ]);

  return {
    company,
    valuation,
    facts,
    calculatedMetrics: calculatedMetricsPayload.metrics,
    thesis,
    claims,
    thesisSections,
    thesisChanges,
    memoryItems,
    sourceDocuments,
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

export async function createResearchClaim(ticker: string, formData: FormData) {
  const normalizedTicker = ticker.toUpperCase();
  const statement = String(formData.get('statement') ?? '').trim();
  const claimType = String(formData.get('claim_type') ?? 'thesis').trim() || 'thesis';
  const materiality = Number(formData.get('materiality_score') ?? 5);

  if (statement.length < 5) return;

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
  const sourceTier = String(formData.get('source_tier') ?? 'secondary').trim() || 'secondary';
  const sourceRef = String(formData.get('source_ref') ?? '').trim();
  const [sourceRefType, sourceRefId] = sourceRef.split(':');
  const parsedSourceRefId = Number(sourceRefId);
  const documentId = sourceRefType === 'document' ? parsedSourceRefId : Number(formData.get('document_id') ?? 0);
  const documentChunkId = sourceRefType === 'chunk' ? parsedSourceRefId : Number(formData.get('document_chunk_id') ?? 0);

  if (summary.length < 3) return;

  await postJson(`/api/memory/claims/${claimId}/evidence`, null, {
    evidence_type: evidenceType === 'contradicts' ? 'contradicts' : 'supports',
    summary,
    source_url: sourceUrl || null,
    source_tier: sourceTier,
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
  const sourceTier = String(formData.get('source_tier') ?? 'primary').trim() || 'primary';
  const materiality = Number(formData.get('materiality_score') ?? 5);

  if (statement.length < 5 || summary.length < 3 || !Number.isFinite(chunkId) || chunkId <= 0) return;

  const claim = await postJson<ResearchClaim | null>('/api/memory/claims', null, {
    ticker: normalizedTicker,
    statement,
    claim_type: 'source_extracted',
    materiality_score: Number.isFinite(materiality) ? Math.max(0, Math.min(10, materiality)) : 5,
    source_quality: sourceTier,
    created_by: 'user',
  });

  if (!claim?.id) return;

  await postJson(`/api/memory/claims/${claim.id}/evidence`, null, {
    evidence_type: evidenceType === 'contradicts' ? 'contradicts' : 'supports',
    summary,
    source_url: sourceUrl || null,
    source_tier: sourceTier,
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
  const sourceTier = String(formData.get('source_tier') ?? 'primary').trim() || 'primary';

  if (!Number.isFinite(claimId) || claimId <= 0 || summary.length < 3 || !Number.isFinite(chunkId) || chunkId <= 0) return;

  await postJson(`/api/memory/claims/${claimId}/evidence`, null, {
    evidence_type: evidenceType === 'contradicts' ? 'contradicts' : 'supports',
    summary,
    source_url: sourceUrl || null,
    source_tier: sourceTier,
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

  if (summary.length < 5) return;

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

  if (content.length < 3) return;

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
      sources: [],
      blocked: true,
      proposed_actions: ['Check backend status'],
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

export async function importResearchDocumentFile(formData: FormData) {
  const ticker = String(formData.get('ticker') ?? '').trim().toUpperCase();
  const title = String(formData.get('title') ?? '').trim();
  const file = formData.get('file');

  if (!ticker || !title || !(file instanceof File) || file.size === 0) return;

  await postForm('/api/sources/documents/ingest-file', null, formData);
  revalidatePath('/research/sources');
  revalidatePath(`/research/${ticker}`);
}

export async function importResearchDocumentUrl(formData: FormData) {
  const ticker = String(formData.get('ticker') ?? '').trim().toUpperCase();
  const title = String(formData.get('title') ?? '').trim();
  const url = String(formData.get('url') ?? '').trim();
  const sourceType = String(formData.get('source_type') ?? 'url').trim() || 'url';

  if (!ticker || !title || !url) return;

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
): Promise<{ ticker?: string | null; event_type: string; materiality_score: number; impact_direction: string; summary: string }> {
  const text = String(formData.get('text') ?? '').trim();
  const source = String(formData.get('source') ?? 'manual').trim();
  const url = String(formData.get('url') ?? '').trim();
  if (!text || text.length < 20) return { ticker: null, event_type: 'unknown', materiality_score: 0, impact_direction: 'neutral', summary: '' };

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
  if (!rawItems) {
    return { status: 'empty', received: 0, created: 0, skipped_duplicates: 0, requires_update: 0 };
  }

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
  } catch {
    return { status: 'invalid_json', received: 0, created: 0, skipped_duplicates: 0, requires_update: 0 };
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

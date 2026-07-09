from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str
    exchange: str
    currency: str
    sector: str
    industry: str
    cik: str | None
    ir_url: str | None
    company_type: str
    valuation_model: str
    special_sources: list[str]
    special_risks: list[str]
    factor_tags: list[str]


class FinancialFactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    metric: str
    value: Decimal
    unit: str
    period: str
    fiscal_year: int | None
    fiscal_quarter: str | None
    source_id: int | None
    source_type: str
    is_reported: bool
    is_adjusted: bool
    confidence: Decimal
    created_at: datetime


class FinancialRefreshResponse(BaseModel):
    status: str
    ticker: str
    provider: str
    source_document_id: int
    facts_imported: int
    statements_imported: int
    latest_periods: dict[str, str | None]
    valuation_input_ready: bool


class CalculatedMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    company_id: int | None = None
    metric: str
    value: Decimal | None
    unit: str
    period: str
    fiscal_year: int | None = None
    fiscal_quarter: str | None = None
    status: str
    definition_version: str
    formula: str
    numerator: Decimal | None
    denominator: Decimal | None
    source_fact_ids: list[int]
    calculation_trace: dict
    confidence: Decimal


class CalculatedMetricsResponse(BaseModel):
    ticker: str
    status: str
    metrics: list[CalculatedMetricOut]


class ThesisGenerateRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    force_new_version: bool = False


class ThesisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    version: int
    status: str
    thesis_markdown: str
    executive_summary: str
    rating: str
    current_price: Decimal
    bear_value: Decimal
    base_value: Decimal
    bull_value: Decimal
    expected_value: Decimal
    margin_of_safety: Decimal
    data_confidence_score: int
    source_coverage_score: int
    red_team_score: int
    valuation_risk_score: int
    input_fingerprint: str | None = None
    created_at: datetime


class ClaimEvidenceCreate(BaseModel):
    document_id: int | None = None
    document_chunk_id: int | None = None
    source_url: str | None = None
    evidence_type: str = Field(
        default="supports",
        pattern="^(supports|contradicts|supersedes|context|uncertain)$",
    )
    summary: str = Field(min_length=3)
    quote: str | None = None
    confidence: Decimal = Decimal("0.70")
    source_tier: str | None = None


class ClaimEvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: int
    document_id: int | None
    document_chunk_id: int | None
    source_url: str | None
    evidence_type: str
    summary: str
    quote: str | None
    confidence: Decimal
    source_tier: str
    created_at: datetime


class ClaimCreate(BaseModel):
    ticker: str | None = Field(default=None, max_length=20)
    company_id: int | None = None
    thesis_version_id: int | None = None
    statement: str = Field(min_length=5)
    claim_type: str = "thesis"
    status: str = "unverified"
    confidence: Decimal = Decimal("0.50")
    materiality_score: int = Field(default=5, ge=0, le=10)
    source_quality: str = "unknown"
    created_by: str = "user"


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int | None
    thesis_version_id: int | None
    statement: str
    claim_type: str
    status: str
    confidence: Decimal
    materiality_score: int
    source_quality: str
    created_by: str
    last_reviewed_at: datetime | None
    evidence: list[ClaimEvidenceOut] = Field(default_factory=list)
    created_at: datetime


class ThesisSectionCreate(BaseModel):
    section_key: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    status: str = "draft"
    order_index: int = 0
    confidence: Decimal = Decimal("0.70")


class ThesisSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thesis_version_id: int
    company_id: int
    section_key: str
    title: str
    body: str
    status: str
    order_index: int
    confidence: Decimal
    created_at: datetime
    updated_at: datetime


class ThesisChangeCreate(BaseModel):
    ticker: str | None = Field(default=None, max_length=20)
    company_id: int | None = None
    from_version_id: int | None = None
    to_version_id: int | None = None
    change_type: str = "manual"
    impact_direction: str = Field(default="neutral", pattern="^(positive|negative|neutral|mixed)$")
    materiality_score: int = Field(default=5, ge=0, le=10)
    summary: str = Field(min_length=5)
    affected_claim_ids: list[int] = Field(default_factory=list)
    affected_metrics: list[str] = Field(default_factory=list)
    requires_review: bool = False


class ThesisChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int | None
    from_version_id: int | None
    to_version_id: int | None
    change_type: str
    impact_direction: str
    materiality_score: int
    summary: str
    affected_claim_ids: list[int]
    affected_metrics: list[str]
    requires_review: bool
    created_at: datetime
    updated_at: datetime


class ResearchSessionCreate(BaseModel):
    ticker: str | None = Field(default=None, max_length=20)
    company_id: int | None = None
    title: str = Field(min_length=1, max_length=300)
    question: str = Field(min_length=3)
    status: str = "open"
    summary: str = ""
    source_ids: list[int] = Field(default_factory=list)
    claim_ids: list[int] = Field(default_factory=list)


class ResearchSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int | None
    title: str
    question: str
    status: str
    summary: str
    source_ids: list[int]
    claim_ids: list[int]
    memory_item_ids: list[int]
    created_at: datetime
    updated_at: datetime


class MemoryItemCreate(BaseModel):
    ticker: str | None = Field(default=None, max_length=20)
    company_id: int | None = None
    research_session_id: int | None = None
    scope: str = "portfolio"
    memory_type: str = "note"
    importance: int = Field(default=5, ge=0, le=10)
    content: str = Field(min_length=3)
    status: str = "active"
    source_type: str = "user"
    source_id: int | None = None


class MemoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int | None
    research_session_id: int | None
    scope: str
    memory_type: str
    importance: int
    content: str
    status: str
    source_type: str
    source_id: int | None
    created_at: datetime
    updated_at: datetime


class ManualNewsRequest(BaseModel):
    text: str = Field(min_length=10)
    url: str | None = None
    source: str = "manual"


class ManualNewsResponse(BaseModel):
    ticker: str | None
    summary: str
    event_type: str
    materiality_score: int
    impact_direction: str
    affected_thesis: bool
    affected_assumptions: list[str]
    requires_update: bool
    action: str
    source_policy: str
    source_tier: str = "tier_unknown"
    source_trust_score: float = 0
    portfolio_weight: float = 0
    materiality_reasons: list[str] = Field(default_factory=list)
    model_route: str = "news_triage"
    affected_claim_ids: list[int] = Field(default_factory=list)
    affected_node_ids: list[int] = Field(default_factory=list)
    semantic_impact: dict = Field(default_factory=dict)


class NewsFeedItem(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    text: str | None = None
    ticker: str | None = Field(default=None, max_length=20)
    url: str | None = None
    source: str = "feed"
    published_at: datetime | None = None


class NewsIngestRequest(BaseModel):
    items: list[NewsFeedItem] = Field(min_length=1, max_length=100)
    source: str = "feed"


class NewsIngestResponse(BaseModel):
    status: str
    received: int
    created: int
    skipped_duplicates: int
    requires_update: int
    events: list[ManualNewsResponse]


class ChatRequest(BaseModel):
    question: str = Field(min_length=3)
    scope: str = "portfolio"
    ticker: str | None = None


class SynthesisSection(BaseModel):
    key: Literal[
        "facts",
        "calculations",
        "user_hypotheses",
        "inferences",
        "contradictions",
        "insufficient_data",
        "conclusion",
    ]
    body: str
    citations: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    sections: list[SynthesisSection] = Field(default_factory=list)
    sources: list[dict]
    blocked: bool = False
    proposed_actions: list[str] = Field(default_factory=list)
    evidence_suggestions: list[dict] = Field(default_factory=list)
    prompt_version: str | None = None
    model: str | None = None


class EvidenceSuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int | None
    document_id: int | None
    document_chunk_id: int | None
    suggested_claim_id: int | None
    suggestion_type: str
    statement: str
    relation: str
    rationale: str
    quote: str | None
    confidence: Decimal
    status: str
    model: str | None
    prompt_version: str
    metadata_: dict
    created_at: datetime


class EvidenceSuggestionAction(BaseModel):
    action: Literal["accept", "reject"]
    claim_id: int | None = None


class ContradictionScanRequest(BaseModel):
    ticker: str
    document_id: int | None = None
    news_event_id: int | None = None
    create_reviews: bool = True


class ResearchReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int | None
    review_type: str
    status: str
    priority: str
    title: str
    summary: str
    thesis_change_id: int | None
    claim_id: int | None
    news_event_id: int | None
    assigned_to: str | None
    due_at: datetime | None
    resolved_at: datetime | None
    resolution_notes: str | None
    created_at: datetime
    updated_at: datetime


class ResearchReviewUpdate(BaseModel):
    status: Literal["open", "in_progress", "approved", "dismissed", "resolved"]
    resolution_notes: str | None = None


class ResearchAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int | None
    review_id: int | None
    severity: str
    status: str
    alert_type: str
    title: str
    message: str
    fingerprint: str
    channels: list[str]
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    snoozed_until: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResearchAlertAction(BaseModel):
    action: Literal["acknowledge", "resolve", "snooze", "reopen"]
    actor: str = "user"
    snoozed_until: datetime | None = None


class ResearchAlertChannels(BaseModel):
    channels: list[Literal["in_app", "email", "push"]] = Field(
        min_length=1
    )


class ThesisNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    thesis_version_id: int
    node_key: str
    node_type: str
    label: str
    description: str
    status: str
    confidence: Decimal
    materiality_score: int
    claim_ids: list[int]
    invalidation_conditions: list[str]


class ThesisEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_node_id: int
    to_node_id: int
    edge_type: str
    strength: Decimal


class ThesisGraphOut(BaseModel):
    ticker: str
    thesis_version_id: int
    nodes: list[ThesisNodeOut]
    edges: list[ThesisEdgeOut]


class EarningsWorkflowRequest(BaseModel):
    fiscal_year: int
    fiscal_quarter: str = Field(default="FY", pattern="^(Q1|Q2|Q3|Q4|FY)$")
    document_ids: list[int] = Field(default_factory=list)
    force_new_thesis: bool = False


class EarningsRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    fiscal_year: int
    fiscal_quarter: str
    status: str
    document_ids: list[int]
    extracted_metrics: list[dict]
    guidance_changes: list[dict]
    comparisons: dict
    management_tone: dict
    promise_tracking: list[dict]
    risk_updates: list[dict]
    catalyst_updates: list[dict]
    claim_changes: list[dict]
    thesis_change_id: int | None
    error: str | None
    trace: dict
    created_at: datetime


class ValuationResponse(BaseModel):
    ticker: str
    model_type: str
    status: str = "ok"
    publishable: bool = True
    current_price: float | None = None
    bear_value: float | None = None
    base_value: float | None = None
    bull_value: float | None = None
    expected_value: float | None = None
    margin_of_safety: float | None = None
    missing_inputs: list[str] = []
    reverse_dcf: dict = {}
    sensitivity: dict = {}
    moat: dict = {}
    trace: dict = {}

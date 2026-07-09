from datetime import datetime
from decimal import Decimal

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
    evidence_type: str = Field(default="supports", pattern="^(supports|contradicts|context)$")
    summary: str = Field(min_length=3)
    quote: str | None = None
    confidence: Decimal = Decimal("0.70")
    source_tier: str = "secondary"


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


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    blocked: bool = False
    proposed_actions: list[str] = Field(default_factory=list)


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

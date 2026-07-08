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
    created_at: datetime


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


class ChatRequest(BaseModel):
    question: str = Field(min_length=3)
    scope: str = "portfolio"
    ticker: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    blocked: bool = False
    proposed_actions: list[str] = []


class ValuationResponse(BaseModel):
    ticker: str
    model_type: str
    current_price: float
    bear_value: float
    base_value: float
    bull_value: float
    expected_value: float
    margin_of_safety: float
    reverse_dcf: dict
    sensitivity: dict
    trace: dict


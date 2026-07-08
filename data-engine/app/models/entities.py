from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    exchange: Mapped[str] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    sector: Mapped[str] = mapped_column(String(120), default="Unknown")
    industry: Mapped[str] = mapped_column(String(160), default="Unknown")
    cik: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ir_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_type: Mapped[str] = mapped_column(String(80))
    valuation_model: Mapped[str] = mapped_column(String(120))
    special_sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    special_risks: Mapped[list[str]] = mapped_column(JSON, default=list)
    factor_tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    positions: Mapped[list["Position"]] = relationship(back_populates="company")
    thesis_versions: Mapped[list["ThesisVersion"]] = relationship(back_populates="company")


class Position(Base, TimestampMixin):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    market_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    market_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    source: Mapped[str] = mapped_column(String(80), default="demo_seed")
    as_of: Mapped[date] = mapped_column(Date, default=date.today)

    company: Mapped[Company] = relationship(back_populates="positions")


class CashBalance(Base, TimestampMixin):
    __tablename__ = "cash_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String(10), index=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    settled_cash: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    source: Mapped[str] = mapped_column(String(80), default="demo_seed")
    as_of: Mapped[date] = mapped_column(Date, default=date.today)


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    action: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    fees: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(80), index=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    storage_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document")


class DocumentChunk(Base, TimestampMixin):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    document: Mapped[Document] = relationship(back_populates="chunks")


class FinancialFact(Base, TimestampMixin):
    __tablename__ = "financial_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    metric: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    unit: Mapped[str] = mapped_column(String(40), default="USD")
    period: Mapped[str] = mapped_column(String(40))
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fiscal_quarter: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(80), default="seed")
    is_reported: Mapped[bool] = mapped_column(Boolean, default=True)
    is_adjusted: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.80"))


class FinancialStatement(Base, TimestampMixin):
    __tablename__ = "financial_statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    statement_type: Mapped[str] = mapped_column(String(40))
    period: Mapped[str] = mapped_column(String(40))
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fiscal_quarter: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    facts: Mapped[dict] = mapped_column(JSON, default=dict)


class MarketPrice(Base, TimestampMixin):
    __tablename__ = "market_prices"
    __table_args__ = (UniqueConstraint("company_id", "date", name="uq_market_price_company_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    adj_close: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    volume: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(80), default="seed")


class NewsEvent(Base, TimestampMixin):
    __tablename__ = "news_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    title: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(120), default="manual")
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    event_type: Mapped[str] = mapped_column(String(80), default="unknown")
    materiality_score: Mapped[int] = mapped_column(Integer, default=0)
    impact_direction: Mapped[str] = mapped_column(String(40), default="neutral")
    affected_thesis: Mapped[bool] = mapped_column(Boolean, default=False)
    affected_assumptions: Mapped[list[str]] = mapped_column(JSON, default=list)
    requires_update: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExternalClaim(Base, TimestampMixin):
    __tablename__ = "external_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    claim: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(80))
    metric: Mapped[str | None] = mapped_column(String(120), nullable=True)
    period: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.80"))
    used_in_model: Mapped[bool] = mapped_column(Boolean, default=False)


class Transcript(Base, TimestampMixin):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    period: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    transcript_text: Mapped[str] = mapped_column(Text, default="")


class CallClaim(Base, TimestampMixin):
    __tablename__ = "call_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    transcript_id: Mapped[int] = mapped_column(ForeignKey("transcripts.id"), index=True)
    speaker: Mapped[str] = mapped_column(String(160))
    speaker_role: Mapped[str] = mapped_column(String(120))
    claim: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(80))
    metric: Mapped[str | None] = mapped_column(String(120), nullable=True)
    period: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.80"))
    follow_up_required: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="open")
    later_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    linked_result_id: Mapped[int | None] = mapped_column(ForeignKey("financial_facts.id"), nullable=True)


class Catalyst(Base, TimestampMixin):
    __tablename__ = "catalysts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    catalyst_type: Mapped[str] = mapped_column(String(80))
    materiality_score: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(40), default="open")
    source_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)


class ValuationModel(Base, TimestampMixin):
    __tablename__ = "valuation_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    model_type: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    calculation_trace: Mapped[dict] = mapped_column(JSON, default=dict)


class ValuationAssumption(Base, TimestampMixin):
    __tablename__ = "valuation_assumptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    valuation_model_id: Mapped[int] = mapped_column(ForeignKey("valuation_models.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    value: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    unit: Mapped[str] = mapped_column(String(40), default="decimal")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scenario: Mapped[str] = mapped_column(String(40), default="base")
    source_type: Mapped[str] = mapped_column(String(80), default="user")
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assumption_type: Mapped[str] = mapped_column(String(80), default="model")
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.70"))
    is_user_override: Mapped[bool] = mapped_column(Boolean, default=False)


class ValuationOutput(Base, TimestampMixin):
    __tablename__ = "valuation_outputs"

    id: Mapped[int] = mapped_column(primary_key=True)
    valuation_model_id: Mapped[int] = mapped_column(ForeignKey("valuation_models.id"), index=True)
    scenario: Mapped[str] = mapped_column(String(40), default="base")
    equity_value: Mapped[Decimal] = mapped_column(Numeric(24, 2), default=0)
    value_per_share: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    margin_of_safety: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class ThesisVersion(Base, TimestampMixin):
    __tablename__ = "thesis_versions"
    __table_args__ = (UniqueConstraint("company_id", "version", name="uq_thesis_company_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    thesis_markdown: Mapped[str] = mapped_column(Text)
    executive_summary: Mapped[str] = mapped_column(Text)
    rating: Mapped[str] = mapped_column(String(40), default="watch")
    current_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    bear_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    base_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    bull_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    expected_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    margin_of_safety: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    data_confidence_score: Mapped[int] = mapped_column(Integer, default=0)
    source_coverage_score: Mapped[int] = mapped_column(Integer, default=0)
    red_team_score: Mapped[int] = mapped_column(Integer, default=0)
    valuation_risk_score: Mapped[int] = mapped_column(Integer, default=0)

    company: Mapped[Company] = relationship(back_populates="thesis_versions")


class ThesisDiff(Base, TimestampMixin):
    __tablename__ = "thesis_diffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    from_version_id: Mapped[int | None] = mapped_column(ForeignKey("thesis_versions.id"), nullable=True)
    to_version_id: Mapped[int | None] = mapped_column(ForeignKey("thesis_versions.id"), nullable=True)
    change_summary: Mapped[str] = mapped_column(Text)
    affected_assumptions: Mapped[list[str]] = mapped_column(JSON, default=list)
    rating_changed: Mapped[bool] = mapped_column(Boolean, default=False)


class SourceAudit(Base, TimestampMixin):
    __tablename__ = "source_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    thesis_version_id: Mapped[int | None] = mapped_column(ForeignKey("thesis_versions.id"), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    source_coverage_score: Mapped[int] = mapped_column(Integer, default=0)
    unsupported_claims: Mapped[list[str]] = mapped_column(JSON, default=list)
    weak_claims: Mapped[list[str]] = mapped_column(JSON, default=list)
    data_conflicts: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_fixes: Mapped[list[str]] = mapped_column(JSON, default=list)


class RiskEvent(Base, TimestampMixin):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    severity: Mapped[str] = mapped_column(String(40), default="info")
    event_type: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    metric_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="open")


class DailyBrief(Base, TimestampMixin):
    __tablename__ = "daily_briefs"

    id: Mapped[int] = mapped_column(primary_key=True)
    brief_date: Mapped[date] = mapped_column(Date, unique=True)
    markdown: Mapped[str] = mapped_column(Text)
    alerts: Mapped[list[dict]] = mapped_column(JSON, default=list)
    source_count: Mapped[int] = mapped_column(Integer, default=0)


class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="Research chat")
    scope: Mapped[str] = mapped_column(String(80), default="portfolio")
    messages: Mapped[list[dict]] = mapped_column(JSON, default=list)
    source_ids: Mapped[list[int]] = mapped_column(JSON, default=list)


class ModelRun(Base, TimestampMixin):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow: Mapped[str] = mapped_column(String(120), index=True)
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model: Mapped[str] = mapped_column(String(160))
    prompt_version: Mapped[str] = mapped_column(String(120), default="unknown")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class BudgetUsage(Base, TimestampMixin):
    __tablename__ = "budget_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    usage_date: Mapped[date] = mapped_column(Date, index=True)
    model: Mapped[str] = mapped_column(String(160))
    workflow: Mapped[str] = mapped_column(String(120))
    cost_eur: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)


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


class TenantOwnedMixin:
    """Marks rows that must be isolated by the active Research OS tenant."""

    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id"), nullable=True, index=True
    )


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="Research workspace")
    status: Mapped[str] = mapped_column(String(40), default="active")
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


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
    claims: Mapped[list["Claim"]] = relationship(back_populates="company")
    memory_items: Mapped[list["MemoryItem"]] = relationship(back_populates="company")


class Position(TenantOwnedMixin, Base, TimestampMixin):
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


class CashBalance(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "cash_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String(10), index=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    settled_cash: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    source: Mapped[str] = mapped_column(String(80), default="demo_seed")
    as_of: Mapped[date] = mapped_column(Date, default=date.today)


class Transaction(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_transaction_tenant_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    action: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    fees: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Document(TenantOwnedMixin, Base, TimestampMixin):
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


class DocumentChunk(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    document: Mapped[Document] = relationship(back_populates="chunks")


class FinancialFact(TenantOwnedMixin, Base, TimestampMixin):
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


class CalculatedMetric(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "calculated_metrics"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "metric",
            "period",
            "definition_version",
            name="uq_calculated_metric_definition_period",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    metric: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    unit: Mapped[str] = mapped_column(String(40), default="decimal")
    period: Mapped[str] = mapped_column(String(40), index=True)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fiscal_quarter: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="ok")
    definition_version: Mapped[str] = mapped_column(String(80), default="v1")
    formula: Mapped[str] = mapped_column(Text)
    numerator: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    denominator: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    source_fact_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    calculation_trace: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.70"))


class FinancialStatement(TenantOwnedMixin, Base, TimestampMixin):
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


class NewsEvent(TenantOwnedMixin, Base, TimestampMixin):
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


class ExternalClaim(TenantOwnedMixin, Base, TimestampMixin):
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


class Transcript(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    period: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    transcript_text: Mapped[str] = mapped_column(Text, default="")


class CallClaim(TenantOwnedMixin, Base, TimestampMixin):
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


class Catalyst(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "catalysts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    catalyst_type: Mapped[str] = mapped_column(String(80))
    materiality_score: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(40), default="open")
    source_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)


class ValuationModel(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "valuation_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    model_type: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    calculation_trace: Mapped[dict] = mapped_column(JSON, default=dict)


class ValuationAssumption(TenantOwnedMixin, Base, TimestampMixin):
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


class ValuationOutput(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "valuation_outputs"

    id: Mapped[int] = mapped_column(primary_key=True)
    valuation_model_id: Mapped[int] = mapped_column(ForeignKey("valuation_models.id"), index=True)
    scenario: Mapped[str] = mapped_column(String(40), default="base")
    equity_value: Mapped[Decimal] = mapped_column(Numeric(24, 2), default=0)
    value_per_share: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    margin_of_safety: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class ThesisVersion(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "thesis_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "version", name="uq_thesis_tenant_company_version"
        ),
    )

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
    input_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    company: Mapped[Company] = relationship(back_populates="thesis_versions")


class ThesisDiff(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "thesis_diffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    from_version_id: Mapped[int | None] = mapped_column(ForeignKey("thesis_versions.id"), nullable=True)
    to_version_id: Mapped[int | None] = mapped_column(ForeignKey("thesis_versions.id"), nullable=True)
    change_summary: Mapped[str] = mapped_column(Text)
    affected_assumptions: Mapped[list[str]] = mapped_column(JSON, default=list)
    rating_changed: Mapped[bool] = mapped_column(Boolean, default=False)


class ThesisSection(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "thesis_sections"
    __table_args__ = (
        UniqueConstraint("thesis_version_id", "section_key", name="uq_thesis_section_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    thesis_version_id: Mapped[int] = mapped_column(ForeignKey("thesis_versions.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    section_key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.70"))
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class Claim(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    thesis_version_id: Mapped[int | None] = mapped_column(ForeignKey("thesis_versions.id"), nullable=True)
    statement: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(80), default="thesis")
    status: Mapped[str] = mapped_column(String(40), default="unverified")
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.50"))
    materiality_score: Mapped[int] = mapped_column(Integer, default=5)
    source_quality: Mapped[str] = mapped_column(String(40), default="unknown")
    created_by: Mapped[str] = mapped_column(String(80), default="system")
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    company: Mapped[Company | None] = relationship(back_populates="claims")
    evidence: Mapped[list["ClaimEvidence"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class ClaimEvidence(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "claim_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    document_chunk_id: Mapped[int | None] = mapped_column(ForeignKey("document_chunks.id"), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(40), default="supports")
    summary: Mapped[str] = mapped_column(Text)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.70"))
    source_tier: Mapped[str] = mapped_column(String(40), default="secondary")
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    claim: Mapped[Claim] = relationship(back_populates="evidence")


class ThesisChange(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "thesis_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    from_version_id: Mapped[int | None] = mapped_column(ForeignKey("thesis_versions.id"), nullable=True)
    to_version_id: Mapped[int | None] = mapped_column(ForeignKey("thesis_versions.id"), nullable=True)
    change_type: Mapped[str] = mapped_column(String(80), default="update")
    impact_direction: Mapped[str] = mapped_column(String(40), default="neutral")
    materiality_score: Mapped[int] = mapped_column(Integer, default=5)
    summary: Mapped[str] = mapped_column(Text)
    affected_claim_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    affected_metrics: Mapped[list[str]] = mapped_column(JSON, default=list)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)


class ResearchSession(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "research_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="open")
    summary: Mapped[str] = mapped_column(Text, default="")
    source_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    claim_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    memory_item_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class MemoryItem(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "memory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    research_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_sessions.id"), nullable=True, index=True
    )
    scope: Mapped[str] = mapped_column(String(80), default="portfolio")
    memory_type: Mapped[str] = mapped_column(String(80), default="note")
    importance: Mapped[int] = mapped_column(Integer, default=5)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="active")
    source_type: Mapped[str] = mapped_column(String(80), default="user")
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    company: Mapped[Company | None] = relationship(back_populates="memory_items")


class SourceAudit(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "source_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    thesis_version_id: Mapped[int | None] = mapped_column(ForeignKey("thesis_versions.id"), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    source_coverage_score: Mapped[int] = mapped_column(Integer, default=0)
    unsupported_claims: Mapped[list[str]] = mapped_column(JSON, default=list)
    weak_claims: Mapped[list[str]] = mapped_column(JSON, default=list)
    data_conflicts: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_fixes: Mapped[list[str]] = mapped_column(JSON, default=list)


class RiskEvent(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    severity: Mapped[str] = mapped_column(String(40), default="info")
    event_type: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    metric_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="open")


class DailyBrief(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "daily_briefs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "brief_date", name="uq_daily_brief_tenant_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    brief_date: Mapped[date] = mapped_column(Date)
    markdown: Mapped[str] = mapped_column(Text)
    alerts: Mapped[list[dict]] = mapped_column(JSON, default=list)
    source_count: Mapped[int] = mapped_column(Integer, default=0)


class ChatSession(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="Research chat")
    scope: Mapped[str] = mapped_column(String(80), default="portfolio")
    messages: Mapped[list[dict]] = mapped_column(JSON, default=list)
    source_ids: Mapped[list[int]] = mapped_column(JSON, default=list)


class ModelRun(TenantOwnedMixin, Base, TimestampMixin):
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


class BudgetUsage(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "budget_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    usage_date: Mapped[date] = mapped_column(Date, index=True)
    model: Mapped[str] = mapped_column(String(160))
    workflow: Mapped[str] = mapped_column(String(120))
    cost_eur: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)


class EvidenceSuggestion(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "evidence_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    document_chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_chunks.id"), nullable=True, index=True
    )
    suggested_claim_id: Mapped[int | None] = mapped_column(ForeignKey("claims.id"), nullable=True)
    suggestion_type: Mapped[str] = mapped_column(String(80), default="create_claim")
    statement: Mapped[str] = mapped_column(Text)
    relation: Mapped[str] = mapped_column(String(40), default="uncertain")
    rationale: Mapped[str] = mapped_column(Text, default="")
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.50"))
    status: Mapped[str] = mapped_column(String(40), default="pending")
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(120), default="evidence-suggestion-v1")
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class ResearchReview(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "research_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    review_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(40), default="medium")
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    thesis_change_id: Mapped[int | None] = mapped_column(
        ForeignKey("thesis_changes.id"), nullable=True
    )
    claim_id: Mapped[int | None] = mapped_column(ForeignKey("claims.id"), nullable=True)
    news_event_id: Mapped[int | None] = mapped_column(ForeignKey("news_events.id"), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(160), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class ThesisNode(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "thesis_nodes"
    __table_args__ = (
        UniqueConstraint(
            "thesis_version_id", "node_key", name="uq_thesis_node_version_key"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    thesis_version_id: Mapped[int] = mapped_column(ForeignKey("thesis_versions.id"), index=True)
    node_key: Mapped[str] = mapped_column(String(160))
    node_type: Mapped[str] = mapped_column(String(80), default="assumption")
    label: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="active")
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.50"))
    materiality_score: Mapped[int] = mapped_column(Integer, default=5)
    claim_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    invalidation_conditions: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class ThesisEdge(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "thesis_edges"
    __table_args__ = (
        UniqueConstraint(
            "from_node_id", "to_node_id", "edge_type", name="uq_thesis_edge"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("thesis_nodes.id"), index=True)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("thesis_nodes.id"), index=True)
    edge_type: Mapped[str] = mapped_column(String(80), default="depends_on")
    strength: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class ResearchAlert(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "research_alerts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "fingerprint", name="uq_research_alert_fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    review_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_reviews.id"), nullable=True
    )
    severity: Mapped[str] = mapped_column(String(40), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    alert_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(160))
    channels: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["in_app"])
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class ConnectorState(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "connector_states"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "connector", "company_id", "feed_url", name="uq_connector_state"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connector: Mapped[str] = mapped_column(String(80), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    feed_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cursor: Mapped[str | None] = mapped_column(String(500), nullable=True)
    etag: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class EarningsRun(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "earnings_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer)
    fiscal_quarter: Mapped[str] = mapped_column(String(10), default="FY")
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    document_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    extracted_metrics: Mapped[list[dict]] = mapped_column(JSON, default=list)
    guidance_changes: Mapped[list[dict]] = mapped_column(JSON, default=list)
    comparisons: Mapped[dict] = mapped_column(JSON, default=dict)
    management_tone: Mapped[dict] = mapped_column(JSON, default=dict)
    promise_tracking: Mapped[list[dict]] = mapped_column(JSON, default=list)
    risk_updates: Mapped[list[dict]] = mapped_column(JSON, default=list)
    catalyst_updates: Mapped[list[dict]] = mapped_column(JSON, default=list)
    claim_changes: Mapped[list[dict]] = mapped_column(JSON, default=list)
    thesis_change_id: Mapped[int | None] = mapped_column(
        ForeignKey("thesis_changes.id"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace: Mapped[dict] = mapped_column(JSON, default=dict)


class MoatAssessment(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "moat_assessments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "moat_type", name="uq_tenant_company_moat_type"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    moat_type: Mapped[str] = mapped_column(String(80))
    strength: Mapped[int] = mapped_column(Integer, default=0)
    trend: Mapped[str] = mapped_column(String(40), default="uncertain")
    persistence: Mapped[str] = mapped_column(String(80), default="unknown")
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.0"))
    status: Mapped[str] = mapped_column(String(40), default="insufficient_evidence")
    supporting_claim_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    contradicting_claim_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    assessment_trace: Mapped[dict] = mapped_column(JSON, default=dict)


class PeerRelationship(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "peer_relationships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "peer_company_id",
            name="uq_tenant_company_peer_relationship",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    peer_company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(80), default="automatic")
    rationale: Mapped[list[str]] = mapped_column(JSON, default=list)
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    selection_trace: Mapped[dict] = mapped_column(JSON, default=dict)


class RedTeamRun(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "red_team_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    thesis_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("thesis_versions.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="completed")
    score: Mapped[int] = mapped_column(Integer, default=0)
    strongest_bear_case: Mapped[str] = mapped_column(Text, default="")
    findings: Mapped[list[dict]] = mapped_column(JSON, default=list)
    broken_assumptions: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_risks: Mapped[list[str]] = mapped_column(JSON, default=list)
    falsification_tests: Mapped[list[str]] = mapped_column(JSON, default=list)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(120), default="red-team-v1")
    trace: Mapped[dict] = mapped_column(JSON, default=dict)

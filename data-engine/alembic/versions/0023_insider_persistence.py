"""0023 insider persistence

Durable Form 4/4-A storage: one immutable insider_filings row per SEC
accession (amendments never mutate the original) and insider_transactions
keyed by a stable row fingerprint so re-ingestion is idempotent. Basis for
the watchlist monitor and the durable alert outbox.
"""

import sqlalchemy as sa

from alembic import op

revision = "0023_insider_persistence"
down_revision = "0022_thesis_professional_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insider_filings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("accession_number", sa.String(40), nullable=False),
        sa.Column("form", sa.String(10), nullable=False),
        sa.Column("is_amendment", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("amends_accession", sa.String(40), nullable=True),
        sa.Column("issuer_cik", sa.String(20), nullable=False),
        sa.Column("issuer_ticker", sa.String(20), nullable=True),
        sa.Column("issuer_name", sa.String(300), nullable=True),
        sa.Column("filing_date", sa.String(20), nullable=True),
        sa.Column("report_date", sa.String(20), nullable=True),
        sa.Column("period_of_report", sa.String(20), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("index_url", sa.String(1000), nullable=True),
        sa.Column("raw_sha256", sa.String(64), nullable=True),
        sa.Column("parser_version", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="parsed"),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "accession_number", name="uq_insider_filings_tenant_accession"),
    )
    op.create_index("ix_insider_filings_issuer", "insider_filings", ["issuer_cik"])
    op.create_index("ix_insider_filings_tenant_id", "insider_filings", ["tenant_id"])

    op.create_table(
        "insider_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("filing_id", sa.Integer(), sa.ForeignKey("insider_filings.id"), nullable=False),
        sa.Column("accession_number", sa.String(40), nullable=False),
        sa.Column("form", sa.String(10), nullable=False),
        sa.Column("issuer_ticker", sa.String(20), nullable=True),
        sa.Column("insider", sa.String(500), nullable=True),
        sa.Column("insider_cik", sa.String(20), nullable=True),
        sa.Column("role", sa.String(300), nullable=True),
        sa.Column("officer_title", sa.String(300), nullable=True),
        sa.Column("multi_reporter", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attribution", sa.String(30), nullable=True),
        sa.Column("code", sa.String(10), nullable=True),
        sa.Column("acquired_disposed", sa.String(5), nullable=True),
        sa.Column("shares", sa.Float(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("tx_date", sa.String(20), nullable=True),
        sa.Column("is_derivative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("data_quality", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "fingerprint", name="uq_insider_transactions_tenant_fingerprint"),
    )
    op.create_index("ix_insider_transactions_filing", "insider_transactions", ["filing_id"])
    op.create_index("ix_insider_transactions_ticker_date", "insider_transactions", ["issuer_ticker", "tx_date"])
    op.create_index("ix_insider_transactions_tenant_id", "insider_transactions", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("insider_transactions")
    op.drop_table("insider_filings")

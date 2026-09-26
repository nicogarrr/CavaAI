"""0026 dividend records

Declared dividend records ingested from a labeled data provider (FMP).
Deduped per (company, ex_date, amount); used for real dividend-yield
analytics. Dividend cash application to the ledger stays manual.
"""

import sqlalchemy as sa

from alembic import op

revision = "0026_dividend_records"
down_revision = "0025_company_domicile_country"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dividend_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(24, 10), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
        sa.Column("source", sa.String(40), nullable=False, server_default="fmp"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("company_id", "ex_date", "amount", name="uq_dividend_record"),
    )
    op.create_index("ix_dividend_records_company_id", "dividend_records", ["company_id"])
    op.create_index("ix_dividend_records_ex_date", "dividend_records", ["ex_date"])


def downgrade() -> None:
    op.drop_index("ix_dividend_records_ex_date", table_name="dividend_records")
    op.drop_index("ix_dividend_records_company_id", table_name="dividend_records")
    op.drop_table("dividend_records")

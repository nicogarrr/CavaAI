"""0028 fund managers + 13F holdings

Reviewed institutional managers tracked via SEC Form 13F and their
information-table holdings stored as filed (CUSIP + issuer name, tickers
never inferred; amendments immutable).
"""

import sqlalchemy as sa
from alembic import op

revision = "0028_fund_manager_holdings"
down_revision = "0027_corporate_action_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fund_managers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("cik", sa.String(10), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("last_report_date", sa.Date(), nullable=True),
        sa.Column("coverage", sa.String(20), nullable=False, server_default="ok"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("cik", name="uq_fund_manager_cik"),
    )
    op.create_index("ix_fund_managers_cik", "fund_managers", ["cik"])
    op.create_table(
        "manager_holdings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column(
            "manager_id", sa.Integer(), sa.ForeignKey("fund_managers.id"), nullable=False
        ),
        sa.Column("accession_number", sa.String(25), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("is_amendment", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("name_of_issuer", sa.String(200), nullable=False, server_default=""),
        sa.Column("title_of_class", sa.String(150), nullable=False, server_default=""),
        sa.Column("cusip", sa.String(9), nullable=False),
        sa.Column("value_usd_thousands", sa.Numeric(20, 2), nullable=True),
        sa.Column("shares", sa.Numeric(24, 4), nullable=True),
        sa.Column("share_type", sa.String(10), nullable=False, server_default="SH"),
        sa.Column("put_call", sa.String(10), nullable=False, server_default=""),
        sa.Column("investment_discretion", sa.String(10), nullable=False, server_default=""),
        sa.Column("voting_sole", sa.Numeric(24, 0), nullable=True),
        sa.Column("voting_shared", sa.Numeric(24, 0), nullable=True),
        sa.Column("voting_none", sa.Numeric(24, 0), nullable=True),
        sa.Column("filing_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("source", sa.String(40), nullable=False, server_default="sec_edgar_13f"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "manager_id",
            "accession_number",
            "cusip",
            "title_of_class",
            "put_call",
            name="uq_manager_holding",
        ),
    )
    op.create_index("ix_manager_holdings_manager_id", "manager_holdings", ["manager_id"])
    op.create_index(
        "ix_manager_holdings_accession_number", "manager_holdings", ["accession_number"]
    )


def downgrade() -> None:
    op.drop_index("ix_manager_holdings_accession_number", table_name="manager_holdings")
    op.drop_index("ix_manager_holdings_manager_id", table_name="manager_holdings")
    op.drop_table("manager_holdings")
    op.drop_index("ix_fund_managers_cik", table_name="fund_managers")
    op.drop_table("fund_managers")

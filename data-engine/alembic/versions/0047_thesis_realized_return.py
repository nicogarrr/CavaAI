"""D3: retorno realizado de la tesis (tesis ↔ mercado)."""
import sqlalchemy as sa

from alembic import op

revision = "0047_thesis_realized_return"
down_revision = "0046_inferred_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thesis_realized_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column(
            "thesis_version_id",
            sa.Integer(),
            sa.ForeignKey("thesis_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("thesis_version", sa.Integer(), nullable=False),
        sa.Column("thesis_published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("thesis_status", sa.String(40), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=True),
        sa.Column("entry_price", sa.Numeric(20, 6), nullable=True),
        sa.Column(
            "entry_price_status", sa.String(40), nullable=False, server_default="missing"
        ),
        sa.Column("entry_price_rule", sa.Text(), nullable=False, server_default=""),
        sa.Column("fair_value_at_entry", sa.Numeric(20, 6), nullable=True),
        sa.Column(
            "fair_value_source", sa.String(40), nullable=False, server_default="absent"
        ),
        sa.Column("upside_at_entry", sa.Numeric(12, 6), nullable=True),
        sa.Column("holding_horizon_days", sa.Integer(), nullable=False, server_default="180"),
        sa.Column(
            "holding_horizon_source", sa.String(40), nullable=False, server_default="default_6m"
        ),
        sa.Column("judgement_horizon", sa.String(10), nullable=False, server_default="6M"),
        sa.Column(
            "judgement_status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column("horizons", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False, server_default="inconclusive"),
        sa.Column(
            "outcome_definition_version", sa.String(20), nullable=False, server_default="v1"
        ),
        sa.Column("verdict_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "counts_toward_hit_rate", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("benchmark_ticker", sa.String(20), nullable=True),
        sa.Column(
            "benchmark_status", sa.String(40), nullable=False, server_default="missing"
        ),
        sa.Column("base_currency", sa.String(10), nullable=False, server_default="EUR"),
        sa.Column(
            "decision_lesson_id",
            sa.Integer(),
            sa.ForeignKey("decision_lessons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "decision_lesson_link", sa.String(60), nullable=False, server_default="none"
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("price_fingerprint", sa.String(64), nullable=False, server_default=""),
        sa.Column("revisions", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "thesis_version_id",
            name="uq_thesis_realized_return_tenant_version",
        ),
    )
    op.create_index(
        "ix_thesis_realized_returns_tenant_id", "thesis_realized_returns", ["tenant_id"]
    )
    op.create_index(
        "ix_thesis_realized_returns_company_id", "thesis_realized_returns", ["company_id"]
    )
    op.create_index(
        "ix_thesis_realized_returns_ticker", "thesis_realized_returns", ["ticker"]
    )
    op.create_index(
        "ix_thesis_realized_returns_thesis_version_id",
        "thesis_realized_returns",
        ["thesis_version_id"],
    )
    op.create_index(
        "ix_thesis_realized_returns_decision_lesson_id",
        "thesis_realized_returns",
        ["decision_lesson_id"],
    )
    op.create_index(
        "ix_thesis_realized_returns_company_outcome",
        "thesis_realized_returns",
        ["company_id", "outcome"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_thesis_realized_returns_company_outcome", table_name="thesis_realized_returns"
    )
    op.drop_index(
        "ix_thesis_realized_returns_decision_lesson_id",
        table_name="thesis_realized_returns",
    )
    op.drop_index(
        "ix_thesis_realized_returns_thesis_version_id", table_name="thesis_realized_returns"
    )
    op.drop_index("ix_thesis_realized_returns_ticker", table_name="thesis_realized_returns")
    op.drop_index(
        "ix_thesis_realized_returns_company_id", table_name="thesis_realized_returns"
    )
    op.drop_index(
        "ix_thesis_realized_returns_tenant_id", table_name="thesis_realized_returns"
    )
    op.drop_table("thesis_realized_returns")

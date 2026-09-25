"""0031 propick runs + candidates

Persistence for the ProPicks deterministic funnel (big-data stage): one row
per run with the full parameter set, one row per evaluated company with
pass/fail, score, failed gates, metrics snapshot and coverage declaration.
Failed rows are kept on purpose: the gates a company fails are product
information, and keeping the whole universe makes runs diffable (in/out)
for the rebalance digest.
"""

import sqlalchemy as sa
from alembic import op

revision = "0031_propick_runs"
down_revision = "0030_indexes_and_cascades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "propick_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="completed"),
        sa.Column("funnel_version", sa.String(80), nullable=False),
        sa.Column("universe_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("top_n", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_propick_runs_as_of", "propick_runs", ["as_of"])
    op.create_index("ix_propick_runs_status", "propick_runs", ["status"])
    op.create_index("ix_propick_runs_tenant_id", "propick_runs", ["tenant_id"])
    op.create_table(
        "propick_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("propick_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False
        ),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("failed_gates", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("coverage", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "company_id", name="uq_propick_candidates_run_company"),
    )
    op.create_index("ix_propick_candidates_run_id", "propick_candidates", ["run_id"])
    op.create_index(
        "ix_propick_candidates_run_score", "propick_candidates", ["run_id", "score"]
    )
    op.create_index("ix_propick_candidates_company_id", "propick_candidates", ["company_id"])
    op.create_index("ix_propick_candidates_tenant_id", "propick_candidates", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("propick_candidates")
    op.drop_table("propick_runs")

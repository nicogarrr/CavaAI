"""Forward paper proposals, tenant scoped and immutable execution prices."""
import sqlalchemy as sa

from alembic import op

revision = "0051_paper_trading"
down_revision = "0050_thesis_backtest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("proposal_key", sa.String(120), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("horizon", sa.String(16), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("conviction", sa.Numeric(8, 4), nullable=False),
        sa.Column("author", sa.String(8), nullable=False),
        sa.Column("inference_label", sa.String(16), nullable=False),
        sa.Column("inference_basis", sa.Text(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("close_reason", sa.String(20), nullable=True),
        sa.Column("price_source", sa.String(80), nullable=True),
        sa.UniqueConstraint("tenant_id", "proposal_key", name="uq_paper_proposal"),
    ]
    for name in ("proposed_entry", "stop", "target", "quantity", "entry_price", "mark_price", "exit_price"):
        columns.append(sa.Column(name, sa.Numeric(20, 6), nullable=name.endswith("price")))
    for name in ("entry_at", "mark_at", "exit_at", "created_at", "updated_at"):
        columns.append(sa.Column(name, sa.DateTime(timezone=True), nullable=name not in {"created_at", "updated_at"}))
    op.create_table("paper_trades", *columns)
    op.create_index("ix_paper_trades_tenant_id", "paper_trades", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("paper_trades")

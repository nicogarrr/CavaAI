"""0038 tenant-scoped, versioned portfolio movement digest."""
import sqlalchemy as sa

from alembic import op

revision = "0038_portfolio_move_digests"
down_revision = "0037_market_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("portfolio_move_digests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("digest_date", sa.Date(), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("coverage", sa.String(40), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "digest_date", "version", "input_hash", name="uq_portfolio_move_digest_version"))
    op.create_index("ix_portfolio_move_digests_tenant_id", "portfolio_move_digests", ["tenant_id"])
    op.create_index("ix_portfolio_move_digests_digest_date", "portfolio_move_digests", ["digest_date"])
    op.create_index("ix_portfolio_move_digests_tenant_date", "portfolio_move_digests", ["tenant_id", "digest_date"])


def downgrade() -> None:
    op.drop_table("portfolio_move_digests")

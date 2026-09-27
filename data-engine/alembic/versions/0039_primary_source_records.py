"""Explicit primary-source provenance link."""
import sqlalchemy as sa

from alembic import op

revision = "0039_primary_source_records"
down_revision = "0038_portfolio_move_digests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "primary_source_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id")),
        sa.Column("news_event_id", sa.Integer(), sa.ForeignKey("news_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_url", sa.String(2000), nullable=False),
        sa.Column("final_url", sa.String(2000), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reference_kind", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "news_event_id", "final_url", "checksum", name="uq_primary_source_event_url_hash"),
    )
    for name in ("tenant_id", "news_event_id", "document_id"):
        op.create_index(f"ix_primary_source_records_{name}", "primary_source_records", [name])


def downgrade() -> None:
    op.drop_table("primary_source_records")

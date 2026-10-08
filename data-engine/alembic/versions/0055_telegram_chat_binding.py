"""Verified Telegram ownership, fail closed for existing subscriptions."""
import sqlalchemy as sa

from alembic import op

revision = "0055_telegram_chat_binding"
down_revision = "0054_alert_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, extra in (
        ("telegram_link_challenges", [
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("candidate_chat_id", sa.String(32)),
            sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        ]),
        ("telegram_chat_bindings", [
            sa.Column("chat_id", sa.String(32), nullable=False, unique=True),
            sa.UniqueConstraint("tenant_id", "user_id", name="uq_telegram_binding_owner"),
        ]),
    ):
        op.create_table(name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("user_id", sa.String(160), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), *extra)
        op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])


def downgrade() -> None:
    op.drop_table("telegram_chat_bindings")
    op.drop_table("telegram_link_challenges")

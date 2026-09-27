"""Estado durable de crédito agotado de TypeSafe."""
import sqlalchemy as sa

from alembic import op

revision = "0042_typesafe_status"
down_revision = "0041_itu_notices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("typesafe_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_billing_failure_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_table("typesafe_status")

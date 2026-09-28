"""ISIN de la empresa (para Modelo 720 y verificación de país emisor)."""
import sqlalchemy as sa

from alembic import op

revision = "0043_company_isin"
down_revision = "0042_typesafe_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("isin", sa.String(length=12), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "isin")

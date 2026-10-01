"""Base por accion de los escenarios de la tesis (ADR ratio, valores cotizados)."""
import sqlalchemy as sa

from alembic import op

revision = "0045_thesis_valuation_basis"
down_revision = "0044_thesis_narrative_sections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "thesis_versions",
        sa.Column("valuation_basis", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("thesis_versions", "valuation_basis")

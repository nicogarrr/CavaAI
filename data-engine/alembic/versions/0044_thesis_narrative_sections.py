"""Secciones de narrativa de la tesis (Análisis narrativo del memo)."""
import sqlalchemy as sa

from alembic import op

revision = "0044_thesis_narrative_sections"
down_revision = "0043_company_isin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "thesis_versions",
        sa.Column("narrative_sections", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("thesis_versions", "narrative_sections")

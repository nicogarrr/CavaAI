"""calculated metrics table

Revision ID: 0003_calculated_metrics
Revises: 0002_research_memory
Create Date: 2026-07-09 00:00:00
"""

from alembic import op

from app import models  # noqa: F401
from app.core.database import Base

revision = "0003_calculated_metrics"
down_revision = "0002_research_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["calculated_metrics"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["calculated_metrics"].drop(bind=bind, checkfirst=True)

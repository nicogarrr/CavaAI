"""research memory tables

Revision ID: 0002_research_memory
Revises: 0001_initial
Create Date: 2026-07-09 00:00:00
"""

from alembic import op
from app import models  # noqa: F401
from app.core.database import Base

revision = "0002_research_memory"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

NEW_TABLES = [
    "thesis_sections",
    "claims",
    "claim_evidence",
    "thesis_changes",
    "research_sessions",
    "memory_items",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in NEW_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(NEW_TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)

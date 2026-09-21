"""metadata JSON en news_events (Jev doc-type en ingesta de noticias)

Revision ID: 0020_news_event_metadata
Revises: 0019_watchlist
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_news_event_metadata"
down_revision = "0019_watchlist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("news_events", sa.Column("metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("news_events", "metadata")

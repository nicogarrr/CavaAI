"""0027 corporate action source provenance

source + fetched_at on corporate_actions so auto-ingested splits from a
labeled data provider are distinguishable from manual entries. Ingested
actions stay unapplied until the user applies them explicitly.
"""

import sqlalchemy as sa
from alembic import op

revision = "0027_corporate_action_source"
down_revision = "0026_dividend_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "corporate_actions",
        sa.Column("source", sa.String(40), nullable=False, server_default="manual"),
    )
    op.add_column(
        "corporate_actions",
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("corporate_actions", "fetched_at")
    op.drop_column("corporate_actions", "source")

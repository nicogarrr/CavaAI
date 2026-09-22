"""0022 thesis professional fields

Adds the structures a professional investment thesis needs and the current
template cannot express: an explicit hypothesis, dated catalysts, invalidation
criteria (what evidence would kill the thesis) and bear/base/bull scenario
probabilities. All nullable: existing versions keep working and the generator
fills them from already-collected data where possible.
"""

import sqlalchemy as sa
from alembic import op

revision = "0022_thesis_professional_fields"
down_revision = "0021_perf_hot_path_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("thesis_versions") as batch:
        batch.add_column(sa.Column("hypothesis", sa.Text(), nullable=True))
        batch.add_column(sa.Column("catalysts", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("invalidation_criteria", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("scenario_probabilities", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("thesis_versions") as batch:
        batch.drop_column("scenario_probabilities")
        batch.drop_column("invalidation_criteria")
        batch.drop_column("catalysts")
        batch.drop_column("hypothesis")

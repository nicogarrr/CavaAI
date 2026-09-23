"""0025 company domicile country

Issuer domicile country for global-first country exposure. Nullable and
never guessed: positions without a known domicile keep falling back to the
listing-exchange map and then to "Unknown".
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_company_domicile_country"
down_revision = "0024_workflow_run_envelope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("domicile_country", sa.String(120), nullable=True),
    )


# ADVERTENCIA DOWNGRADE DESTRUCTIVO: drop_column pierde los valores de
# domicile_country. Re-subir recrea la columna vacia (NULL): el
# backfill nunca se recupera solo.
def downgrade() -> None:
    op.drop_column("companies", "domicile_country")

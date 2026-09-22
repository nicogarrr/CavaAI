"""0029 manager holding filing date

filing_date on manager_holdings so the quarter-over-quarter comparison can
pick the latest accession per report period deterministically (amendments
supersede base filings in the comparison view).
"""

import sqlalchemy as sa
from alembic import op

revision = "0029_manager_holding_filing_date"
down_revision = "0028_fund_manager_holdings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manager_holdings", sa.Column("filing_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("manager_holdings", "filing_date")

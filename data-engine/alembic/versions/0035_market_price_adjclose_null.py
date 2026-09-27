"""0035 market_prices.adj_close admite NULL (spot sin ajuste honesto)

Una quote spot no es una serie ajustada por splits/dividendos: escribir
adj_close=close afirmaba un ajuste nunca realizado y el default=0 del modelo
convertia el None honesto en un 0 que hundia los retornos compuestos. NULL es
la representacion honesta; los consumidores ya tratan falsy como "sin dato".
"""

import sqlalchemy as sa

from alembic import op

revision = "0035_market_price_adjclose_null"
down_revision = "0034_market_price_volume_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table: sqlite (tests de migracion) no soporta ALTER COLUMN
    # directo; en Postgres emite el mismo ALTER COLUMN de siempre.
    with op.batch_alter_table("market_prices") as batch_op:
        batch_op.alter_column("adj_close", existing_type=sa.Numeric(20, 6), nullable=True)


def downgrade() -> None:
    # Cerrado en fallo: restaurar NOT NULL con filas NULL exigiria borrarlas o
    # fabricar un ajuste. Decision humana previa, nunca silenciosa.
    bind = op.get_bind()
    null_rows = bind.execute(
        sa.text("SELECT count(*) FROM market_prices WHERE adj_close IS NULL")
    ).scalar()
    if null_rows:
        raise RuntimeError(
            f"Downgrade 0035 abortado: {null_rows} filas de market_prices tienen "
            "adj_close NULL. Restaurar NOT NULL implicaria borrarlas o fabricar "
            "un ajuste; rellena o elimina esas filas a mano antes de revertir."
        )
    with op.batch_alter_table("market_prices") as batch_op:
        batch_op.alter_column("adj_close", existing_type=sa.Numeric(20, 6), nullable=False)

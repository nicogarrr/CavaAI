"""0034 market_prices.volume admite NULL (volumen desconocido honesto)

Las fuentes spot (FMP quote sin volumen, Finnhub quote) no dan el volumen
del dia. Hasta aqui la fila se escribia con volume=0: un dato fabricado que
coronaba al ticker como el menos activo en movers y ensuciaba "Mas activas"
con ceros. NULL es la representacion honesta de "la fuente no lo da".
Las filas historicas con 0 NO se reescriben aqui: no se puede distinguir un
0 real de un 0 fabricado sin la fuente; su limpieza es decision de datos.
"""

import sqlalchemy as sa

from alembic import op

revision = "0034_market_price_volume_null"
down_revision = "0033_alert_deliveries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("market_prices", "volume", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Cerrado en fallo: los NULL no caben de vuelta en NOT NULL y borrarlos en
    # silencio destruiria barras legitimas (volumen desconocido no es fila
    # defectuosa). El downgrade exige una decision humana previa.
    bind = op.get_bind()
    null_rows = bind.execute(
        sa.text("SELECT count(*) FROM market_prices WHERE volume IS NULL")
    ).scalar()
    if null_rows:
        raise RuntimeError(
            f"Downgrade 0034 abortado: {null_rows} filas de market_prices tienen "
            "volume NULL. Restaurar NOT NULL implicaria borrarlas; rellena o "
            "elimina esas filas a mano antes de revertir."
        )
    op.alter_column("market_prices", "volume", existing_type=sa.Integer(), nullable=False)

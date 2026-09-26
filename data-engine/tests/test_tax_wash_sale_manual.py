"""Wash-sale segun el procedimiento del Manual AEAT 2025 (art. 33.5.f LIRPF).

Casos sacados de Manual Renta 2025, cap. 11, apdo. E ("Procedimiento para la
imputacion de las perdidas patrimoniales en caso de recompra de valores
homogeneos"), verificado en
https://sede.agenciatributaria.gob.es/Sede/ayuda/manuales-videos-folletos/manuales-practicos/irpf-2025/c11-ganancias-perdidas-patrimoniales/ganancias-perdidas-patrimoniales-que-no-bi/perdidas-patrimoniales-que-no-se-tales.html
(actualizado 17/03/2026). Ley: art. 33.5.f-g Ley 35/2006 (BOE-A-2006-20764).

Regla pineada: recompra previa = min(remanente tras la venta, comprado en
los 2 meses previos), absorbida FIFO sobre los lotes supervivientes en
ventana; excepcion de compra unica sin tenencia inicial; posteriores tambien
cuentan; informe siempre orientativo (fiscal_disclaimer).

Hermetico: SQLite en memoria, EUR (sin FX), sin red.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, Portfolio, Transaction
from app.services.tax_report_service import TaxReportService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _eur_portfolio(db: Session) -> None:
    db.add(Portfolio(name="Main", base_currency="EUR", is_default=True))
    db.commit()


def _company(db: Session, ticker: str) -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="XETRA", currency="EUR",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _tx(db, company, day, action, qty, price, fees="0"):
    db.add(Transaction(
        company_id=company.id, trade_date=day, action=action,
        quantity=Decimal(str(qty)), price=Decimal(str(price)),
        fees=Decimal(str(fees)), currency="EUR",
    ))
    db.commit()


def test_manual_nada_tras_venta_integra(db):
    """Manual E.1: si despues no quedan valores, la perdida se imputa integra."""
    _eur_portfolio(db)
    c = _company(db, "M1")
    _tx(db, c, date(2026, 1, 5), "buy", 100, 10)
    _tx(db, c, date(2026, 1, 10), "sell", 100, 8)  # -200, venta total
    _tx(db, c, date(2026, 6, 1), "buy", 1, 8)  # cierra la ventana de datos
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "M1")
    (sale,) = row["sales"]
    assert sale["wash_sale_blocked"] is False
    assert sale["gain_native"] == -200.0
    assert sale["blocked_loss_native"] == 0.0
    assert sale["wash_sale_window_open"] is False


def test_manual_remanente_mayor_que_comprado_previo(db):
    """Manual E.1: remanente (130) >= comprado previo (30) -> recompra = 30."""
    _eur_portfolio(db)
    c = _company(db, "M2")
    _tx(db, c, date(2025, 10, 1), "buy", 200, 10)  # fuera de ventana
    _tx(db, c, date(2026, 1, 5), "buy", 30, 10)  # en ventana previa
    _tx(db, c, date(2026, 1, 10), "sell", 100, 8)  # FIFO vende lote oct: -200
    _tx(db, c, date(2026, 6, 1), "buy", 1, 8)  # cierra la ventana de datos
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "M2")
    (sale,) = row["sales"]
    assert sale["wash_sale_blocked"] is True
    assert sale["blocked_loss_native"] == 60.0  # 30 x 2/accion
    assert sale["gain_native"] == -140.0  # resto computable
    assert sale["wash_sale_window_open"] is False


def test_manual_remanente_menor_que_comprado_previo(db):
    """Manual E.1: remanente (100) < comprado previo (200) -> recompra = 100."""
    _eur_portfolio(db)
    c = _company(db, "M3")
    _tx(db, c, date(2026, 1, 5), "buy", 100, 10)
    _tx(db, c, date(2026, 1, 8), "buy", 100, 9)
    _tx(db, c, date(2026, 1, 10), "sell", 100, 8)  # FIFO vende el lote @10
    _tx(db, c, date(2026, 6, 1), "buy", 1, 8)  # cierra la ventana de datos
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "M3")
    (sale,) = row["sales"]
    assert sale["blocked_loss_native"] == 200.0
    assert sale["gain_native"] == 0.0
    assert sale["wash_sale_window_open"] is False


def test_manual_excepcion_compra_unica_sin_tenencia(db):
    """Manual E.1: una sola compra previa partiendo de cero no es recompra.

    Compra 100, venta parcial 60: lo que queda (40) es la propia compra
    inicial, no una recompra. Sin esta excepcion el motor bloquearia 80.
    """
    _eur_portfolio(db)
    c = _company(db, "M4")
    _tx(db, c, date(2026, 1, 5), "buy", 100, 10)
    _tx(db, c, date(2026, 1, 10), "sell", 60, 8)  # -120
    _tx(db, c, date(2026, 6, 1), "buy", 1, 8)  # cierra la ventana de datos
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "M4")
    (sale,) = row["sales"]
    assert sale["wash_sale_blocked"] is False
    assert sale["blocked_loss_native"] == 0.0
    assert sale["gain_native"] == -120.0
    assert sale["wash_sale_window_open"] is False


def test_manual_compra_posterior_tambien_bloquea(db):
    """Manual E.1: las compras de los 2 meses siguientes tambien recompran."""
    _eur_portfolio(db)
    c = _company(db, "M5")
    _tx(db, c, date(2026, 1, 5), "buy", 100, 10)
    _tx(db, c, date(2026, 1, 10), "sell", 100, 8)  # -200, venta total
    _tx(db, c, date(2026, 1, 20), "buy", 100, 8)  # recompra posterior
    _tx(db, c, date(2026, 6, 1), "buy", 1, 8)  # cierra la ventana de datos
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "M5")
    (sale,) = row["sales"]
    assert sale["wash_sale_blocked"] is True
    assert sale["blocked_loss_native"] == 200.0
    assert sale["gain_native"] == 0.0
    assert sale["wash_sale_window_open"] is False


def test_manual_fifo_absorcion_lote_mas_antiguo(db):
    """Manual E.3 (FIFO art. 37.2): el diferido cae en el lote retenido
    mas antiguo y aflora al venderlo; el neto economico se conserva."""
    _eur_portfolio(db)
    c = _company(db, "M6")
    _tx(db, c, date(2026, 1, 5), "buy", 100, 10)
    _tx(db, c, date(2026, 1, 8), "buy", 100, 9)
    _tx(db, c, date(2026, 1, 10), "sell", 50, 8)  # -100 sobre el lote @10
    _tx(db, c, date(2026, 6, 1), "sell", 150, 12)  # vende el resto
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "M6")
    first, second = row["sales"]
    assert first["blocked_loss_native"] == 100.0
    assert first["gain_native"] == 0.0
    # Lote @10 retenido (50) absorbe el diferido: 500 + 100 = 600.
    assert second["cost_native"] == 1500.0  # 600 + 900 del lote @9
    assert second["gain_native"] == 300.0
    assert row["gain_native"] == 300.0  # -100 + 400 conservado


def test_informe_siempre_orientativo(db):
    """La app etiqueta el informe como orientativo hasta firma fiscal."""
    _eur_portfolio(db)
    c = _company(db, "M7")
    _tx(db, c, date(2026, 1, 5), "buy", 10, 100)
    _tx(db, c, date(2026, 6, 1), "sell", 10, 150)
    report = TaxReportService().compute_report(db, 2026)
    assert report["summary"]["wash_sale_rule"] == "es-irpf-2m"
    assert report["summary"]["wash_sale_basis"] == "manual-aeat-2025"
    assert "orientativo" in report["summary"]["fiscal_disclaimer"]
    assert "asesor fiscal" in report["summary"]["fiscal_disclaimer"]


def test_manual_historial_incluye_ventas_rentables(db):
    """Secuencia del auditor: venta rentable previa NO puede inflar las
    existencias al inicio de la ventana y desactivar la excepcion de compra
    unica (bloquearia una perdida que AEAT permite computar)."""
    _eur_portfolio(db)
    c = _company(db, "M8")
    _tx(db, c, date(2025, 10, 1), "buy", 100, 10)
    _tx(db, c, date(2025, 11, 1), "sell", 100, 12)  # venta RENTABLE previa
    _tx(db, c, date(2026, 1, 5), "buy", 100, 10)  # compra unica en ventana
    _tx(db, c, date(2026, 1, 10), "sell", 60, 8)  # perdida -2/accion
    _tx(db, c, date(2026, 6, 1), "buy", 1, 8)  # cierra la ventana de datos
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "M8")
    (sale,) = row["sales"]
    assert sale["wash_sale_blocked"] is False
    assert sale["blocked_loss_native"] == 0.0
    assert sale["gain_native"] == -120.0

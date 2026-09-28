"""Tests herméticos del generador del fichero Modelo 720 (sin red).

Layout verificado contra la spec oficial AEAT (modelo_720.pdf): registros
de 500 posiciones, valoraciones 12+2, ISIN en 132-143.

Run from data-engine/:
    pytest tests/test_tax_modelo720_file.py -v
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import (
    Company,
    Portfolio,
    PortfolioDailySnapshot,
    Position,
    PositionDailySnapshot,
    Tenant,
)
from app.services.tax_modelo720_file import RECORD_LEN, Modelo720FileService


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed(db, declarant=None, value="60000"):
    tenant = Tenant(external_id="m720f-test", name="M720F test")
    db.add(tenant)
    db.flush()
    db.info["tenant_id"] = tenant.id
    if declarant is not None:
        tenant.metadata_ = {"tax_declarant": declarant}
    portfolio = Portfolio(
        tenant_id=tenant.id, name="Main", base_currency="EUR", is_default=True
    )
    db.add(portfolio)
    db.flush()
    company = Company(
        ticker="AAPL", name="APPLE INC", exchange="NASDAQ", currency="USD",
        sector="S", industry="I", company_type="imported_holding",
        valuation_model="unassigned", isin="US0378331005",
    )
    db.add(company)
    db.flush()
    db.add(Position(
        tenant_id=tenant.id, company_id=company.id, portfolio_id=portfolio.id,
        quantity=Decimal("10"), average_cost=Decimal("150"),
        market_value=Decimal("1800"), base_currency="EUR", source="ibkr_flex",
    ))
    snap = PortfolioDailySnapshot(
        tenant_id=tenant.id, portfolio_id=portfolio.id,
        snapshot_date=date(2025, 12, 31), base_currency="EUR",
        positions_value_base=Decimal(value), cash_value_base=Decimal("0"),
        total_value_base=Decimal(value),
    )
    db.add(snap)
    db.flush()
    db.add(PositionDailySnapshot(
        tenant_id=tenant.id, portfolio_snapshot_id=snap.id,
        portfolio_id=portfolio.id, company_id=company.id,
        snapshot_date=date(2025, 12, 31), quantity=Decimal("10"),
        market_price_native=Decimal("180"), currency="USD",
        fx_rate=Decimal("1"), market_value_native=Decimal(value),
        market_value_base=Decimal(value),
    ))
    db.commit()
    return tenant


DECLARANT = {
    "nif": "12345678Z",
    "apellidos_nombre": "GARCIA IGLESIAS, NICO",
    "telefono": "600111222",
    "first_acquisition_dates": {"US0378331005": "20230115"},
}


def test_unavailable_without_declarant(db):
    _seed(db, declarant=None)
    result = Modelo720FileService().generate(db, 2025)
    assert result["available"] is False
    assert "tax_declarant" in result["reason"]


def test_unavailable_below_threshold(db):
    _seed(db, declarant=DECLARANT, value="40000")
    result = Modelo720FileService().generate(db, 2025)
    assert result["available"] is False


def test_unavailable_when_category_unknown(db):
    # Snapshot de junio (stale) → categoría "desconocido": no se genera
    # fichero sobre datos no concluyentes.
    tenant = _seed(db, declarant=DECLARANT)
    snap = db.query(PositionDailySnapshot).one()
    snap.snapshot_date = date(2025, 6, 30)
    db.query(PortfolioDailySnapshot).one().snapshot_date = date(2025, 6, 30)
    db.commit()
    result = Modelo720FileService().generate(db, 2025)
    assert result["available"] is False


def test_generates_spec_layout_records(db):
    _seed(db, declarant=DECLARANT)
    result = Modelo720FileService().generate(db, 2025)

    assert result["available"] is True
    assert result["detail_records"] == 1
    lines = result["content"].rstrip("\n").split("\n")
    assert len(lines) == 2
    for line in lines:
        assert len(line) == RECORD_LEN
        line.encode("iso-8859-1")  # codificable en la spec

    summary, detail = lines
    # Tipo 1: cabecera y contador.
    assert summary[0] == "1"
    assert summary[1:4] == "720"
    assert summary[4:8] == "2025"
    assert summary[8:17] == "12345678Z"             # 9-17: NIF (9 posiciones exactas)
    assert summary[17:57].rstrip() == "GARCIA IGLESIAS, NICO"
    assert summary[57] == "T"
    assert summary[58:67] == "600111222"
    assert summary[135:144] == "000000001"          # 1 registro de detalle
    # Suma valoración 1 = 60.000,00 → signo espacio + 15+2 dígitos.
    assert summary[144] == " "
    assert summary[145:162] == "00000000006000000"
    # Tipo 2 (V): campos oficiales en sus posiciones exactas.
    assert detail[0] == "2"
    assert detail[101] == "V"                        # 102: clave bien
    assert detail[102] == "1"                        # 103: subclave participación
    assert detail[128:130] == "US"                   # 129-130: país (prefijo ISIN)
    assert detail[130] == "1"                        # 131: identificación por ISIN
    assert detail[131:143].rstrip() == "US0378331005"  # 132-143: ISIN
    assert detail[189:230].rstrip() == "APPLE INC"   # 190-230: entidad
    assert detail[414:422] == "20230115"             # 415-422: fecha incorporación
    assert detail[422] == "A"                        # 423: origen (primera vez)
    assert detail[431] == " "                        # 432: signo valoración 1
    assert detail[432:446] == "000000060000" + "00"   # 433-446: 60.000,00 (12+2)
    assert detail[447:461] == "00000000000000"       # 448-461: valoración 2 a ceros (V)
    assert detail[461] == "A"                        # 462: anotaciones en cuenta
    assert detail[462:474] == "000000001000"         # 463-474: 10 valores (10+2)
    assert detail[475:480] == "10000"                # 476-480: 100,00 %
    assert detail[480:] == " " * 20                  # 481-500: blancos


def test_missing_isin_excluded_with_reason(db):
    _seed(db, declarant=DECLARANT)
    db.query(Company).one().isin = None
    db.commit()
    result = Modelo720FileService().generate(db, 2025)
    assert result["available"] is False
    assert any("ISIN" in e["reason"] for e in result["excluded"])

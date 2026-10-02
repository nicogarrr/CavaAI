"""Seam del resolver: referencia primero, fallback intacto, renombre mismo FIGI."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Company
from app.services import company_resolver as resolver
from app.services.company_resolver import resolve_companies, resolve_company
from app.services.instrument_reference import normalize_row, upsert_rows

AS_OF = date(2026, 10, 1)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _company(db, ticker: str) -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="X", currency="EUR",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.flush()
    return company


def _ref(db, symbol: str, figi: str | None = None, composite: str | None = None):
    row = normalize_row({"symbol": symbol, "figi": figi or "", "composite_figi": composite or ""}, as_of=AS_OF)
    assert row is not None
    upsert_rows(db, [row], commit=True)


def test_known_ticker_resolves_through_reference(db):
    _company(db, "SAN")
    _ref(db, "SAN.MC", figi="BBG000BSAN01", composite="BBG000BSAN02")
    upsert_rows(db, [normalize_row({"symbol": "SAN", "figi": "BBG000BSAN01",
                                    "composite_figi": "BBG000BSAN02"}, as_of=AS_OF)], commit=True)
    assert resolve_company(db, "SAN.MC").ticker == "SAN"


def test_unknown_ticker_falls_back_exactly_as_before(db):
    _company(db, "SAN")
    # Sin fila de referencia: el fallback de sufijos funciona igual que hoy.
    assert resolve_company(db, "SAN.MC").ticker == "SAN"
    assert resolve_company(db, "NOEXISTE") is None
    assert resolve_company(db, "FALTA.MC") is None
    _company(db, "BRK")
    assert resolve_company(db, "BRK.B") is None


def test_rename_resolves_to_same_figi_company(db):
    company = _company(db, "FAKEOLD")
    _ref(db, "FAKEOLD", figi="BBG000RENA01", composite="BBG000RENA02")
    _ref(db, "FAKENEW", figi="BBG000RENA01", composite="BBG000RENA02")
    assert resolve_company(db, "FAKENEW").id == company.id
    assert resolve_company(db, "FAKEOLD").id == company.id


def test_batch_seam_and_existing_contracts(db):
    san = _company(db, "SAN")
    _company(db, "SAN.MC")  # el exacto siempre gana
    _ref(db, "FAKEOLD", figi="BBG000RENA01", composite="BBG000RENA02")
    _ref(db, "FAKENEW", figi="BBG000RENA01", composite="BBG000RENA02")
    old = _company(db, "FAKEOLD")
    companies, missing = resolve_companies(db, ["SAN.MC", "FAKENEW", "NOEXISTE", "FALTA.MC"])
    by_ticker = {c.ticker: c for c in companies}
    assert by_ticker["SAN.MC"].ticker == "SAN.MC"  # exacto gana, no el base
    assert by_ticker["FAKEOLD"].id == old.id  # renombre -> misma Company
    assert "NOEXISTE" in missing and "FALTA.MC" in missing
    # Ningun contrato existente cambio: firmas y politica intactas.
    assert frozenset({
        "MC", "L", "PA", "AS", "BR", "LS", "DE", "F", "MI", "SW", "VI",
        "HE", "ST", "CO", "OL", "HK", "T", "AX", "TO", "V", "MX", "SA",
    }) == resolver.KNOWN_MARKET_SUFFIXES
    assert san.ticker == "SAN"

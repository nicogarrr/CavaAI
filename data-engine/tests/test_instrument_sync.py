"""Seed desde fixture CSV minimo: conteos, NULL honestos e idempotencia."""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base
from app.services.instrument_reference import get_by_ticker, upsert_rows
from scripts.sync_instruments import normalize_csv_rows, read_csv_rows

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "instruments" / "equities_sample.csv"
AS_OF = date(2026, 10, 1)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as session:
        yield session


def test_fixture_seed_counts_and_idempotence(db):
    raw = read_csv_rows(FIXTURE)
    assert len(raw) == 6  # 5 validas + 1 sin simbolo
    valid, skipped_invalid = normalize_csv_rows(raw, as_of=AS_OF, source="financedatabase")
    assert len(valid) == 5
    assert skipped_invalid == 1
    first = upsert_rows(db, valid, commit=True)
    assert first == {"inserted": 5, "updated": 0, "skipped": 0}
    second = upsert_rows(db, valid, commit=True)
    assert second == {"inserted": 0, "updated": 0, "skipped": 0}


def test_fixture_unknown_fields_are_null_not_invented(db):
    raw = read_csv_rows(FIXTURE)
    valid, _ = normalize_csv_rows(raw, as_of=AS_OF, source="financedatabase")
    upsert_rows(db, valid, commit=True)
    myst = get_by_ticker(db, "MYST")
    assert myst is not None
    # FinanceDatabase no trae estos campos para MYST -> NULL explicito.
    assert myst.sector is None
    assert myst.industry is None
    assert myst.figi is None
    assert myst.isin is None
    san = get_by_ticker(db, "SAN.MC")
    assert san is not None
    assert san.sector == "Financials"
    assert san.figi == "BBG000BSAN01"

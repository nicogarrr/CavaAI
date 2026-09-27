"""P2: data-quality invariants — the guarantees the product standard rests on.

These tests pin cross-cutting invariants rather than single features:
fingerprint uniqueness, watermark monotonicity, freshness-threshold coverage,
no-null contracts on critical fields, and honest-state vocabulary.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — register all tables
from app.core.database import Base
from app.models.entities import (
    Company,
    ConnectorState,
    InsiderFiling,
    InsiderTransaction,
    Tenant,
    ThesisVersion,
)
from app.services.provenance import FRESHNESS_THRESHOLDS_S, Coverage, coverage_for_age


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _company(db, ticker="ACME"):
    company = Company(
        ticker=ticker, name="Acme", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Software", company_type="research_candidate",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.flush()
    return company


def test_insider_fingerprint_uniqueness_enforced(db):
    """The same SEC row can never be stored twice; amendments create new rows.

    NOTE (pinned invariant): the DB constraint is (tenant_id, fingerprint) and
    SQL treats NULLs as distinct, so the backstop binds only with a real
    tenant — single-tenant deployments MUST run with tenant context set, and
    application-level idempotency (#82) remains the first line.
    """
    tenant = Tenant(external_id="t1", name="t1")
    db.add(tenant)
    db.flush()
    _company(db)
    filing = InsiderFiling(
        tenant_id=tenant.id,
        accession_number="0001-24-000001", form="4", issuer_cik="0001234567",
        issuer_ticker="ACME", filing_date="2024-03-16",
        source_url="https://www.sec.gov/x/f4.xml", parser_version="1.0",
    )
    db.add(filing)
    db.flush()
    tx = InsiderTransaction(
        tenant_id=tenant.id,
        filing_id=filing.id, accession_number=filing.accession_number,
        fingerprint="a" * 64, form="4", issuer_ticker="ACME", insider="Jane CEO",
        code="P", tx_date="2024-03-15", shares=100, price=10,
    )
    db.add(tx)
    db.commit()
    dupe = InsiderTransaction(
        tenant_id=tenant.id,
        filing_id=filing.id, accession_number=filing.accession_number,
        fingerprint="a" * 64, form="4", issuer_ticker="ACME", insider="Jane CEO",
        code="P", tx_date="2024-03-15", shares=100, price=10,
    )
    db.add(dupe)
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


def test_watermark_fields_support_monotonic_checks(db):
    """connector_states carries last_success_at + consecutive_errors so every
    monitor can prove monotonic progress and surface degraded states."""
    state = ConnectorState(connector="insider_monitor")
    db.add(state)
    db.commit()
    t1 = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
    state.last_success_at = t1
    db.commit()
    state.last_success_at = datetime.now(UTC).replace(tzinfo=None)
    state.consecutive_errors = 0
    db.commit()
    stored = db.scalar(select(ConnectorState))
    assert stored.last_success_at >= t1
    assert stored.consecutive_errors == 0


def test_freshness_thresholds_cover_registered_connector_families():
    """Every freshness-sensitive source family has an explicit threshold or
    falls back to the conservative default; thresholds are positive."""
    for family, seconds in FRESHNESS_THRESHOLDS_S.items():
        assert seconds > 0, family
    assert "default" in FRESHNESS_THRESHOLDS_S
    # unregistered families degrade to the default, never to "always fresh"
    old = datetime.now(UTC) - timedelta(seconds=FRESHNESS_THRESHOLDS_S["default"] + 60)
    assert coverage_for_age("unregistered_source", old) == Coverage.STALE


def test_thesis_version_critical_fields_non_null():
    """A persisted thesis without its critical content fields is a contract bug."""
    columns = ThesisVersion.__table__.columns
    assert columns["version"].nullable is False
    assert columns["thesis_markdown"].nullable is False
    assert columns["status"].nullable is False
    assert columns["company_id"].nullable is False


def test_company_critical_fields_non_null():
    columns = Company.__table__.columns
    for field in ("ticker", "name"):
        assert columns[field].nullable is False, field


def test_coverage_vocabulary_is_closed():
    """UI can switch exhaustively on coverage; no ad-hoc states may appear."""
    assert {c.value for c in Coverage} == {"ok", "stale", "partial", "unavailable"}

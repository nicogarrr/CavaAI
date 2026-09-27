"""El snapshot macro global nunca mezcla posiciones entre tenants."""
from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, MarketRegimeSnapshot, Position, Tenant
from app.services.market_snapshot_service import build_snapshot, latest_snapshot


def _db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_build_snapshot_never_leaks_positions_across_tenants():
    db = _db()
    company = Company(ticker="ACME", name="Acme", exchange="NASDAQ", currency="USD", sector="Tech", industry="Tech", company_type="holding", valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[])
    db.add(company)
    db.flush()
    for external_id in ("tenant-a", "tenant-b"):
        tenant = Tenant(external_id=external_id, name=external_id, status="active")
        db.add(tenant)
        db.flush()
        db.add(Position(company_id=company.id, tenant_id=tenant.id, quantity=5, average_cost=10))
    db.commit()

    snapshot = build_snapshot(db, date(2026, 9, 27), datetime(2026, 9, 27, 23, 10, tzinfo=UTC))

    beta = snapshot.metrics.get("portfolio_beta", {})
    assert beta["status"] == "no_disponible"
    # Sin holdings, sin ids de empresa y sin valores de cartera en el snapshot.
    assert "positions" not in beta
    assert str(company.id) not in str(snapshot.metrics)


def test_get_serves_stored_marker_and_never_computes_beta_live():
    db = _db()
    db.add(
        MarketRegimeSnapshot(
            snapshot_date=date(2026, 9, 26),
            model_version="macro-context-hmm-v2",
            input_hash="x" * 64,
            metrics={"hmm": {"status": "sin datos"}},
            probabilities={},
            evidence_ids=[],
            coverage="unavailable",
            generated_at=datetime(2026, 9, 26, 23, 10, tzinfo=UTC),
        )
    )
    company = Company(ticker="ACME", name="Acme", exchange="NASDAQ", currency="USD", sector="Tech", industry="Tech", company_type="holding", valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[])
    db.add(company)
    db.flush()
    db.add(Position(company_id=company.id, tenant_id=1, quantity=5, average_cost=10))
    db.commit()

    payload = latest_snapshot(db)
    assert payload["portfolio_beta"]["status"] == "no_disponible"
    assert "positions" not in payload["portfolio_beta"]

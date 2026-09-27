"""F143: el distintivo de tenencia del snapshot refleja la posicion viva
del tenant, no la clase estatica companies.company_type.

Evidencia pre-fix (prod): AAPL, con 12 acciones en la cartera del
tenant, mostraba "candidato de analisis" (company_type=research_candidate
fijado al alta); SPCX, sin posicion del tenant, mostraba "portfolio
holding" (company_type=portfolio_holding heredado de otro contexto - la
Company es global). Ademas 'portfolio_holding' no tenia traduccion y se
renderizaba en ingles por el fallback de label().
"""

from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Company, Position, Tenant
from app.services.company_snapshot_service import CompanySnapshotService


def _company(ticker: str, company_type: str = "research_candidate") -> Company:
    return Company(
        ticker=ticker,
        name=f"{ticker} Inc",
        exchange="NASDAQ",
        currency="USD",
        sector="Tech",
        industry="Software",
        company_type=company_type,
        valuation_model="unassigned",
    )


def _position(company: Company, quantity: str) -> Position:
    return Position(
        company_id=company.id,
        quantity=Decimal(quantity),
        average_cost=Decimal("100"),
        currency="USD",
    )


def _db_with_tenants():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    tenant_a = Tenant(external_id="snap-a", name="Snap A")
    tenant_b = Tenant(external_id="snap-b", name="Snap B")
    db.add_all([tenant_a, tenant_b])
    db.flush()
    return db, tenant_a, tenant_b


def test_in_portfolio_true_only_with_live_position_of_current_tenant():
    db, tenant_a, tenant_b = _db_with_tenants()

    # AAPL: tenant A la tiene en cartera aunque la ficha diga
    # research_candidate (el caso real de F143).
    aapl = _company("AAPL")
    # SPCX: la ficha dice portfolio_holding pero el tenant A NO tiene
    # posicion (la posicion es de otro tenant): no es tenencia suya.
    spcx = _company("SPCX", company_type="portfolio_holding")
    db.add_all([aapl, spcx])
    db.flush()

    db.info["tenant_id"] = tenant_b.id
    db.add(_position(spcx, "5"))  # la posicion de SPCX es del tenant B
    db.flush()
    db.info["tenant_id"] = tenant_a.id
    db.add(_position(aapl, "12"))  # AAPL si es del tenant A
    db.flush()
    db.commit()

    service = CompanySnapshotService()
    snap_aapl = service.build(db, aapl)
    snap_spcx = service.build(db, spcx)
    assert snap_aapl.in_portfolio is True
    assert snap_spcx.in_portfolio is False

    # Y para el tenant B es exactamente al reves.
    db.info["tenant_id"] = tenant_b.id
    assert service.build(db, aapl).in_portfolio is False
    assert service.build(db, spcx).in_portfolio is True


def test_zero_quantity_position_is_not_a_holding():
    db, tenant_a, _ = _db_with_tenants()
    sold = _company("SOLD", company_type="portfolio_holding")
    db.add(sold)
    db.flush()
    db.info["tenant_id"] = tenant_a.id
    db.add(_position(sold, "0"))  # posicion cerrada: no es tenencia
    db.flush()
    db.commit()

    assert CompanySnapshotService().build(db, sold).in_portfolio is False


def test_anonymous_session_never_claims_holding():
    db, tenant_a, _ = _db_with_tenants()
    held = _company("HELD")
    db.add(held)
    db.flush()
    db.info["tenant_id"] = tenant_a.id
    db.add(_position(held, "3"))
    db.flush()
    db.commit()
    db.info.pop("tenant_id", None)

    assert CompanySnapshotService().build(db, held).in_portfolio is False


def test_build_many_marks_holdings_per_tenant():
    db, tenant_a, _ = _db_with_tenants()
    held = _company("HELD")
    watched = _company("WATCH", company_type="portfolio_holding")
    db.add_all([held, watched])
    db.flush()
    db.info["tenant_id"] = tenant_a.id
    db.add(_position(held, "3"))
    db.flush()
    db.commit()

    snapshots = CompanySnapshotService().build_many(db, [held, watched])
    assert snapshots[held.id].in_portfolio is True
    assert snapshots[watched.id].in_portfolio is False

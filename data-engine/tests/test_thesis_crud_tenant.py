"""Thesis CRUD bajo aislamiento tenant (nivel modelo + scoping de sesión).

Cubre: create→read→update→delete en el mismo tenant, invisibilidad
cross-tenant (lectura None ≈ 404 en la ruta, conteo 0), inmutabilidad de
tenant_id y scoping de bulk UPDATE/DELETE.
Hermético: SQLite en memoria compartida (StaticPool), sin red.
"""

from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.entities import Base, Company, ThesisVersion


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _session(engine, tenant_id):
    session = Session(engine)
    session.info["tenant_id"] = tenant_id
    return session


def _company(db: Session, ticker: str = "MSFT") -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    if company is not None:
        return company
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="operating_company",
        valuation_model="standard_dcf", special_sources=[], special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _thesis(db: Session, company: Company, *, version: int = 1, status: str = "draft") -> ThesisVersion:
    row = ThesisVersion(
        company_id=company.id,
        version=version,
        status=status,
        thesis_markdown="# Tesis",
        executive_summary="Resumen ejecutivo.",
        rating="watch",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_same_tenant_crud_cycle():
    engine = _engine()
    db = _session(engine, 101)
    company = _company(db)

    created = _thesis(db, company)
    assert created.tenant_id == 101  # asignado por el hook, no por el caller

    read = db.get(ThesisVersion, created.id)
    assert read is not None and read.executive_summary == "Resumen ejecutivo."

    read.status = "published"
    read.rating = "buy"
    db.commit()
    assert db.get(ThesisVersion, created.id).status == "published"

    db.delete(read)
    db.commit()
    assert db.get(ThesisVersion, created.id) is None
    db.close()


def test_cross_tenant_read_is_isolated():
    engine = _engine()
    db_a = _session(engine, 101)
    db_b = _session(engine, 202)
    company = _company(db_a)
    created = _thesis(db_a, company)

    # Otro tenant: lectura directa None (la ruta lo mapea a 404) y
    # los listados no ven la fila.
    assert db_b.get(ThesisVersion, created.id) is None
    assert db_b.scalar(
        select(ThesisVersion).where(ThesisVersion.id == created.id)
    ) is None
    assert db_b.query(ThesisVersion).count() == 0
    # El tenant dueño la sigue viendo.
    assert db_a.get(ThesisVersion, created.id) is not None
    db_a.close()
    db_b.close()


def test_cross_tenant_write_rejected():
    import pytest

    engine = _engine()
    db_a = _session(engine, 101)
    db_b = _session(engine, 202)
    company = _company(db_a)
    created = _thesis(db_a, company)

    # Crear con tenant ajeno explícito: rechazado en flush.
    db_b.add(
        ThesisVersion(
            company_id=company.id, version=9, status="draft",
            thesis_markdown="# X", executive_summary="Y",
            tenant_id=101,
        )
    )
    with pytest.raises(RuntimeError, match="Cross-tenant"):
        db_b.commit()
    db_b.rollback()

    # Reasignar tenant_id de una fila persistente: rechazado.
    row = db_a.get(ThesisVersion, created.id)
    row.tenant_id = 202
    with pytest.raises(RuntimeError, match="tenant_id is immutable"):
        db_a.commit()
    db_a.rollback()
    db_a.close()
    db_b.close()


def test_bulk_update_cannot_reassign_tenant():
    import pytest

    engine = _engine()
    db = _session(engine, 101)
    company = _company(db)
    _thesis(db, company)

    with pytest.raises(RuntimeError, match="bulk updates"):
        db.execute(update(ThesisVersion).values(tenant_id=202))
    db.rollback()
    db.close()


def test_bulk_update_delete_scoped_to_tenant():
    engine = _engine()
    db_a = _session(engine, 101)
    db_b = _session(engine, 202)
    company = _company(db_a)
    _thesis(db_a, company, version=1)
    _thesis(db_b, company, version=1)

    db_b.execute(update(ThesisVersion).values(status="published"))
    db_b.commit()
    assert db_b.query(ThesisVersion).filter_by(status="published").count() == 1
    # Sin el filtro de tenant el UPDATE habría tocado las filas de A.
    assert db_a.query(ThesisVersion).filter_by(status="published").count() == 0

    db_b.execute(delete(ThesisVersion))
    db_b.commit()
    assert db_b.query(ThesisVersion).count() == 0
    assert db_a.query(ThesisVersion).count() == 1
    db_a.close()
    db_b.close()

"""Diff desde la ultima visita: solo lo creado despues de ``since``."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, Document, FinancialFact, ThesisChange
from app.services.company_changes_service import MAX_ITEMS, changes_since

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _db() -> tuple[Session, Company, Company]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    cs = []
    for t in ("AAA", "BBB"):
        c = Company(ticker=t, name=t, exchange="TEST", currency="USD", sector="x", industry="x",
                    company_type="standard", valuation_model="standard_dcf")
        db.add(c)
        cs.append(c)
    db.flush()
    return db, cs[0], cs[1]


def _doc(db, c, title, at):
    db.add(Document(company_id=c.id, title=title, source_type="sec_filing",
                    source_url=f"https://sec.example/{title}", created_at=at))


def _fact(db, c, metric, at):
    db.add(FinancialFact(company_id=c.id, metric=metric, value=Decimal("1"), unit="USD",
                         period="FY2025", fiscal_year=2025, created_at=at))


def test_only_rows_after_since_and_only_this_company():
    db, a, b = _db()
    old, new = T0 - timedelta(days=3), T0 + timedelta(days=1)
    _doc(db, a, "viejo", old)
    _doc(db, a, "nuevo", new)
    _doc(db, b, "ajeno", new)
    _fact(db, a, "revenue", old)
    _fact(db, a, "revenue", new)
    _fact(db, a, "net_income", new)
    _fact(db, b, "revenue", new)
    db.add(ThesisChange(company_id=a.id, summary="Sube el margen", impact_direction="positive",
                        requires_review=True, created_at=new))
    db.add(ThesisChange(company_id=a.id, summary="antiguo", created_at=old))
    db.add(ThesisChange(company_id=b.id, summary="ajeno", created_at=new))
    db.flush()
    out = changes_since(db, a.id, T0)
    assert out["documentos"]["total"] == 1
    assert [d["titulo"] for d in out["documentos"]["items"]] == ["nuevo"]
    assert out["hechos"]["total"] == 2
    assert {(m["metric"], m["n"]) for m in out["hechos"]["por_metrica"]} == {("revenue", 1), ("net_income", 1)}
    assert [(c["resumen"], c["requiere_revision"]) for c in out["cambios_tesis"]] == [("Sube el margen", True)]


def test_nothing_new_returns_empty_and_naive_since_is_treated_as_utc():
    db, a, _ = _db()
    _doc(db, a, "viejo", T0 - timedelta(days=1))
    db.flush()
    out = changes_since(db, a.id, T0.replace(tzinfo=None))
    assert out["documentos"] == {"total": 0, "items": []}
    assert out["hechos"] == {"total": 0, "por_metrica": []}
    assert out["cambios_tesis"] == []


def test_list_is_capped_but_total_is_real():
    db, a, _ = _db()
    for i in range(MAX_ITEMS + 5):
        _doc(db, a, f"d{i}", T0 + timedelta(hours=i + 1))
    db.flush()
    out = changes_since(db, a.id, T0)
    assert out["documentos"]["total"] == MAX_ITEMS + 5
    assert len(out["documentos"]["items"]) == MAX_ITEMS


def test_changes_since_route_validates_and_returns_diff():
    from fastapi.testclient import TestClient

    import main
    from app.core.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        db.query(Company).filter(Company.ticker == "CHGZ").delete()
        c = Company(ticker="CHGZ", name="Chg", exchange="TEST", currency="USD", sector="x", industry="x",
                    company_type="standard", valuation_model="standard_dcf")
        db.add(c)
        db.flush()
        _doc(db, c, "reciente", datetime.now(UTC))
        db.commit()
    finally:
        db.close()
    client = TestClient(main.app)
    ok = client.get("/api/companies/CHGZ/changes-since", params={"since": "2020-01-01T00:00:00Z"})
    assert ok.status_code == 200
    assert ok.json()["documentos"]["items"][0]["titulo"] == "reciente"
    assert client.get("/api/companies/CHGZ/changes-since", params={"since": "ayer"}).status_code == 422
    assert client.get("/api/companies/NOPE9/changes-since", params={"since": "2020-01-01T00:00:00Z"}).status_code == 404

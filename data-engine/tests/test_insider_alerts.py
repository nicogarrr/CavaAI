"""PR-4: outbox durable de alertas insider (dedupe por fingerprint)."""

from sqlalchemy import select

from app.core.database import SessionLocal, init_db
from app.models.entities import (
    Company,
    InsiderFiling,
    InsiderTransaction,
    ResearchAlert,
)
from app.services import insider_alerts, insider_persistence
from app.services.connectors import form4 as form4_connector

from tests.test_insider_signals import CEO_BUY_XML

FILING = {
    "form": "4",
    "accession_number": "0001234567-24-000201",
    "filing_date": "2024-03-16",
    "report_date": "2024-03-15",
    "document_url": "https://www.sec.gov/Archives/edgar/data/1234567/f4.xml",
    "index_url": "https://www.sec.gov/Archives/edgar/data/1234567/",
}


def _db():
    init_db()
    return SessionLocal()


def _cleanup(db):
    db.query(ResearchAlert).delete()
    db.query(InsiderTransaction).delete()
    db.query(InsiderFiling).delete()
    db.query(Company).filter(Company.ticker.in_(["ACME"])).delete()
    db.commit()


def _seed_big_buy(db, *, accession=FILING["accession_number"], form="4"):
    """Persiste un filing cuyo XML tiene una compra P grande de un CEO."""
    parsed = form4_connector.parse_form4_xml(CEO_BUY_XML)
    filing = {**FILING, "form": form, "accession_number": accession}
    insider_persistence.persist_filing(db, filing, parsed, xml_text=CEO_BUY_XML)
    return parsed


def test_big_buy_and_c_suite_alerts_created_and_deduped():
    db = _db()
    try:
        _cleanup(db)
        _seed_big_buy(db)

        first = insider_alerts.evaluate(db)
        created_types = {
            row.alert_type
            for row in db.scalars(select(ResearchAlert)).all()
        }
        assert "insider_big_buy" in created_types
        assert "insider_c_suite_buy" in created_types
        assert first["alerts_created"] == len(created_types)
        assert first["alerts_created"] >= 2

        second = insider_alerts.evaluate(db)
        assert second["alerts_created"] == 0
        assert second["alerts_existing"] >= 2
        total = len(db.scalars(select(ResearchAlert)).all())
        assert total == len(created_types)

        big = db.scalar(
            select(ResearchAlert).where(ResearchAlert.alert_type == "insider_big_buy")
        )
        assert "mercado abierto o privado" in big.message
        assert big.metadata_["rule_version"] == insider_alerts.RULE_VERSION
        assert big.metadata_["tx_fingerprint"]
        assert big.channels == ["in_app"]
    finally:
        _cleanup(db)
        db.close()


def test_amendment_generates_its_own_alerts():
    """Una 4/A llega con fingerprints propios: nuevas alertas, sin duplicar."""
    db = _db()
    try:
        _cleanup(db)
        _seed_big_buy(db)
        insider_alerts.evaluate(db)
        before = len(db.scalars(select(ResearchAlert)).all())

        _seed_big_buy(db, accession="0001234567-24-000202", form="4/A")
        stats = insider_alerts.evaluate(db)
        after = len(db.scalars(select(ResearchAlert)).all())
        assert stats["alerts_created"] == after - before
        assert after > before
    finally:
        _cleanup(db)
        db.close()


def test_non_p_codes_and_derivatives_never_alert():
    db = _db()
    try:
        _cleanup(db)
        parsed = form4_connector.parse_form4_xml(CEO_BUY_XML)
        insider_persistence.persist_filing(db, FILING, parsed, xml_text=CEO_BUY_XML)
        # Convierte todas las filas persistidas en grants derivados (codigo A).
        for tx in db.scalars(select(InsiderTransaction)).all():
            tx.code = "A"
            tx.is_derivative = True
            db.add(tx)
        db.commit()

        stats = insider_alerts.evaluate(db)
        assert stats["candidates"] == 0
        assert stats["alerts_created"] == 0
        assert len(db.scalars(select(ResearchAlert)).all()) == 0
    finally:
        _cleanup(db)
        db.close()


def test_cluster_buy_requires_three_distinct_insiders():
    db = _db()
    try:
        _cleanup(db)
        parsed = form4_connector.parse_form4_xml(CEO_BUY_XML)
        tx = parsed["transactions"][0]
        company = Company(
            ticker="ACME", name="ACME Test", exchange="NASDAQ",
            company_type="compounders", valuation_model="dcf",
        )
        db.add(company)
        db.flush()
        # Tres compras P de insiders distintos dentro de 30 dias.
        for idx, cik in enumerate(["111", "222", "333"]):
            accession = f"0001234567-24-0003{idx:02d}"
            clone = dict(tx)
            clone["insider_cik"] = cik
            clone["insider"] = f"Insider {cik}"
            clone["value"] = 50_000.0  # por debajo de big_buy: solo cluster
            clone["shares"] = 500.0
            parsed_clone = {"issuer_cik": "1234567", "ticker": "ACME",
                            "issuer_name": "ACME Test", "transactions": [clone]}
            insider_persistence.persist_filing(
                db,
                {**FILING, "accession_number": accession},
                parsed_clone,
                xml_text=None,
            )

        stats = insider_alerts.evaluate(db)
        clusters = db.scalars(
            select(ResearchAlert).where(ResearchAlert.alert_type == "insider_cluster_buy")
        ).all()
        assert len(clusters) == 1
        assert clusters[0].metadata_["insider_count"] == 3
        assert clusters[0].company_id == company.id
        # Sin big_buy: los valores estan por debajo del umbral.
        assert not db.scalars(
            select(ResearchAlert).where(ResearchAlert.alert_type == "insider_big_buy")
        ).all()
        # 3 c_suite (el XML es un CEO) + 1 cluster.
        assert stats["alerts_created"] == 4
    finally:
        _cleanup(db)
        db.close()

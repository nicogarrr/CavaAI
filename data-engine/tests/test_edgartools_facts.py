"""Via edgartools: 10-K/10-Q -> facts con el mapeo canonico (hermetico, sin red).

Fixtures: tests/fixtures/edgartools/ (companyfacts/submissions oficiales en
miniatura, pocos KB). Todo replay local: los payloads se inyectan o se leen
del snapshot; la red jamas se toca.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Company, Document, FinancialFact
from app.services.connectors.edgartools_concepts import (
    concept_to_metric,
    mapping_table,
)
from app.services.connectors.edgartools_facts import (
    anchors_from_submissions,
    facts_from_companyfacts,
    facts_from_edgartools_entity,
)
from app.services.edgartools_ingestion_service import refresh_from_edgartools

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "edgartools"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Guardian hermetico: cualquier intento de red falla el test."""
    import socket

    _real_connect = socket.socket.connect

    def _blocked(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else str(address)
        # Loopback permitido: asyncio (self-pipe en Windows) y SQLite no son red.
        if host in ("127.0.0.1", "::1", "localhost"):
            return _real_connect(self, address, *args, **kwargs)
        raise AssertionError(f"network access forbidden in hermetic edgartools tests ({host})")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def _load_companyfacts() -> dict:
    return json.loads((FIXTURES / "companyfacts" / "CIK0001234567.json").read_text(encoding="utf-8"))


def _load_submissions() -> dict:
    return json.loads((FIXTURES / "submissions" / "CIK0001234567.json").read_text(encoding="utf-8"))


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db, ticker="TSTEDG", industry="Semiconductors"):
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="Technology", industry=industry, company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _by_metric(facts):
    out: dict[str, dict[str, object]] = {}
    for fact in facts:
        out.setdefault(fact["metric"], {})[fact["period"]] = fact["value"]
    return out


def test_concept_map_covers_sec_metric_map_without_duplicating_it():
    from app.services.financial_ingestion_service import SEC_METRIC_MAP

    table = mapping_table()
    table_pairs = {(row["concept"], row["metric"]) for row in table}
    for metric, concepts, _unit in SEC_METRIC_MAP:
        for concept in concepts:
            assert (concept, metric) in table_pairs
    assert concept_to_metric("Revenues") == "revenue"
    assert concept_to_metric("NetIncomeLoss") == "net_income"
    assert concept_to_metric("NoExiste") is None


def test_10k_facts_map_to_canonical_metrics():
    facts, usage = facts_from_companyfacts(_load_companyfacts(), submissions=_load_submissions())
    by_metric = _by_metric(facts)
    # Fusion de alias: gana Revenues (filed mas reciente), una sola vez.
    assert by_metric["revenue"]["2024-09-28:FY"] == Decimal("391035000000")
    assert by_metric["net_income"]["2024-09-28:FY"] == Decimal("93736000000")
    assert by_metric["eps_diluted"]["2024-09-28:FY"] == Decimal("6.11")
    assert by_metric["total_assets"]["2024-09-28:FY"] == Decimal("364980000000")
    assert by_metric["operating_cash_flow"]["2024-09-28:FY"] == Decimal("118254000000")
    # Capex se almacena en negativo (como la via actual).
    assert by_metric["capital_expenditure"]["2024-09-28:FY"] == Decimal("-9447000000")
    # Partes disjuntas se SUMAN (no gana una): 5M + 8M.
    assert by_metric["intangible_assets"]["2024-09-28:FY"] == Decimal("13000000")
    # Alcance: el combinado gana aunque LongTermDebt tenga filed posterior.
    assert by_metric["total_debt"]["2024-09-28:FY"] == Decimal("100000000000")
    assert usage["revenue"]["2024-09-28"] == "Revenues"
    assert usage["total_debt"]["2024-09-28"] == "DebtLongtermAndShorttermCombinedAmount"


def test_quarterly_facts_use_period_labels():
    facts, _usage = facts_from_companyfacts(_load_companyfacts(), submissions=_load_submissions())
    by_metric = _by_metric(facts)
    assert by_metric["revenue"]["2024-06-29:Q3"] == Decimal("85777000000")
    quarterly = [f for f in facts if f["period"] == "2024-06-29:Q3"]
    assert quarterly and all(f["fiscal_year"] is None and f["fiscal_quarter"] == "Q3" for f in quarterly)
    assert all(f["confidence"] == Decimal("0.9") for f in quarterly)
    annual = [f for f in facts if f["period"] == "2024-09-28:FY"]
    assert annual and all(f["fiscal_year"] == 2024 and f["confidence"] == Decimal("0.95") for f in annual)


def test_annual_without_anchors_is_fail_closed():
    facts, _usage = facts_from_companyfacts(_load_companyfacts(), submissions=_load_submissions(), annual_anchors={})
    assert not [f for f in facts if f["period"].endswith(":FY")]
    # Los trimestres siguen su flujo normal.
    assert [f for f in facts if f["period"] == "2024-06-29:Q3"]


def test_facts_are_financialfact_compatible():
    facts, _usage = facts_from_companyfacts(_load_companyfacts(), submissions=_load_submissions())
    required = {"metric", "value", "unit", "period", "fiscal_year", "fiscal_quarter",
                "source_type", "is_reported", "confidence"}
    assert facts
    for fact in facts:
        assert required <= set(fact)
        assert isinstance(fact["value"], Decimal)
        assert fact["source_type"] == "SEC" and fact["is_reported"] is True


def test_anchors_come_from_submissions_recent_window():
    anchors = anchors_from_submissions(_load_submissions())
    assert anchors["0001234567-24-000010"] == "2024-09-28"
    # El 10-Q y el 4/13F no anclan ejercicio.
    assert "0001234567-24-000009" not in anchors


def test_live_entity_facts_normalize_to_same_values():
    """El camino live (EntityFacts) converge al mismo contrato via stub."""

    class _Fact:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    entity = SimpleNamespace(get_all_facts=lambda: [
        _Fact(concept="Revenues", numeric_value=391035000000.0, unit="USD",
              period_start="2023-10-01", period_end="2024-09-28",
              fiscal_year=2024, fiscal_period="FY", filing_date="2024-11-01",
              form_type="10-K", accession="0001234567-24-000010"),
        _Fact(concept="NetIncomeLoss", numeric_value=93736000000.0, unit="USD",
              period_start="2023-10-01", period_end="2024-09-28",
              fiscal_year=2024, fiscal_period="FY", filing_date="2024-11-01",
              form_type="10-K", accession="0001234567-24-000010"),
        _Fact(concept="NoMapeado", numeric_value=1.0, unit="USD",
              period_start="2023-10-01", period_end="2024-09-28",
              fiscal_year=2024, fiscal_period="FY", filing_date="2024-11-01",
              form_type="10-K", accession="0001234567-24-000010"),
    ])
    facts, _usage = facts_from_edgartools_entity(entity, annual_anchors={"0001234567-24-000010": "2024-09-28"})
    by_metric = _by_metric(facts)
    assert by_metric["revenue"]["2024-09-28:FY"] == Decimal("391035000000")
    assert by_metric["net_income"]["2024-09-28:FY"] == Decimal("93736000000")
    assert "NoMapeado" not in {f.get("_concept") for f in facts}


def test_refresh_persists_sec_facts_idempotently(db):
    company = _company(db)
    # Una fila de otra via que jamas debe tocarse.
    db.add(FinancialFact(company_id=company.id, metric="revenue", value=Decimal("1"),
                         unit="USD", period="2024-09-28:FY", fiscal_year=2024,
                         fiscal_quarter="FY", source_type="FMP", is_reported=True))
    db.commit()
    first = refresh_from_edgartools(db, company, force=True, companyfacts=_load_companyfacts(),
                                    submissions=_load_submissions())
    assert first["status"] == "ingested"
    assert first["provider"] == "SEC" and first["pipeline"] == "edgartools"
    assert first["transport"] == "live" and first["snapshot_synced_at"] is None
    assert first["facts_imported"] > 0
    assert "2024-09-28:FY" in first["fy_periods"]
    rows = db.scalars(select(FinancialFact).where(FinancialFact.company_id == company.id)).all()
    sec_rows = [r for r in rows if r.source_type == "SEC"]
    assert len(sec_rows) == first["facts_imported"]
    assert all(r.confidence is not None for r in sec_rows)
    # La fila FMP sobrevive intacta.
    assert [r for r in rows if r.source_type == "FMP"][0].value == Decimal("1")
    document = db.scalar(select(Document).where(Document.id == first["source_document_id"]))
    assert document.metadata_["pipeline"] == "edgartools"
    assert document.metadata_["xbrl_concept_by_metric_period"]["revenue"]["2024-09-28"] == "Revenues"
    second = refresh_from_edgartools(db, company, force=True, companyfacts=_load_companyfacts(),
                                     submissions=_load_submissions())
    assert second["status"] == "ingested"
    again = db.scalars(select(FinancialFact).where(FinancialFact.company_id == company.id)).all()
    assert len(again) == len(rows)


def test_refresh_from_snapshot_declares_transport(db):
    company = _company(db)
    result = refresh_from_edgartools(db, company, force=True, snapshot_root=FIXTURES)
    assert result["status"] == "ingested"
    assert result["transport"] == "snapshot"
    assert result["snapshot_synced_at"] == "2026-09-30T12:00:00+00:00"
    assert result["cik"] == "0001234567"
    assert result["provenance"]["coverage"] == "ok"

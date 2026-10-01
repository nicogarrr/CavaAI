"""Politica de Nico: cada numero es OFICIAL (URL oficial + fecha, verificada
contra el documento persistido) o INFERIDO (base + URLs). Sin tercera categoria."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.entities import (
    Base,
    Company,
    Document,
    FinancialFact,
    FundamentalModelVersion,
)
from app.services.thesis_provenance import (
    ORIGEN_INFERIDO,
    ORIGEN_OFICIAL,
    classify_origin,
)
from app.services.thesis_service import latest_inputs_provenance

SEC = "https://www.sec.gov/Archives/edgar/data/1/x/doc.htm"
OFFICIAL = {
    "url": SEC,
    "date": "2026-08-10",
    "title": "10-Q",
    "source_type": "primary_official",
    "metric": "revenue",
    "fact_value": Decimal("1.0"),
    "unit": "USD",
    "period": "FY2025",
    "is_reported": True,
}


def _item(key, label, facts, source_type="driver_sourced", method="m", value=1.0):
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": "USD",
        "period": "FY2025",
        "method": method,
        "source_fact_ids": facts,
        "confidence": 0.9,
        "source_type": source_type,
    }


def test_dato_with_verified_official_source_is_oficial_with_link_and_date():
    out = classify_origin([_item("revenue", "dato", [1])], {1: OFFICIAL})[0]
    assert out["origen"] == ORIGEN_OFICIAL
    assert out["fuentes"][0]["url"] == SEC and out["fuentes"][0]["fecha"] == "2026-08-10"
    assert out["base_inferencia"] is None


def test_non_official_or_undated_or_http_sources_are_inferido():
    for src in (
        {**OFFICIAL, "source_type": "news"},
        {**OFFICIAL, "date": None},
        {**OFFICIAL, "url": "http://www.sec.gov/a"},
        {**OFFICIAL, "url": "https://evil.example/www.sec.gov/a"},
        None,
    ):
        sources = {} if src is None else {1: src}
        out = classify_origin([_item("revenue", "dato", [1])], sources)[0]
        assert out["origen"] == ORIGEN_INFERIDO
        assert out["fuentes"] == []


def test_partial_citation_is_inferido():
    out = classify_origin([_item("r", "dato", [1, 2])], {1: OFFICIAL})[0]
    assert out["origen"] == ORIGEN_INFERIDO


def test_policy_estimate_and_calculated_are_inferido_with_honest_base_flag():
    items = [
        _item("g", "supuesto", [], "model_policy", "politica conservadora"),
        _item("wacc", "derivado", [1], "calculated_metric", "CAPM"),
        _item("x", "estimacion_llm", [], "llm_estimate", ""),
    ]
    g, wacc, x = classify_origin(items, {1: OFFICIAL})
    assert g["origen"] == wacc["origen"] == x["origen"] == ORIGEN_INFERIDO
    assert g["base_inferencia"] == "politica conservadora" and g["base_documentada"] is False
    assert wacc["urls_inferencia"] == [SEC] and wacc["base_documentada"] is True
    assert x["base_inferencia"] is None and x["base_documentada"] is False


def test_median_ratio_clamp_from_financial_facts_is_inferido():
    # ratio_assumption: mediana de ratios derivados de varios facts, con clamp.
    item = _item("effective_tax_rate", "derivado", [1, 2], "financial_facts")
    out = classify_origin([item], {1: OFFICIAL, 2: OFFICIAL})[0]
    assert out["origen"] == ORIGEN_INFERIDO
    one = _item("fcf_margin", "derivado", [1], "financial_facts")
    assert classify_origin([one], {1: OFFICIAL})[0]["origen"] == ORIGEN_INFERIDO


def test_snapshot_value_not_matching_fact_is_inferido():
    out = classify_origin([_item("revenue", "dato", [1], value=999.0)], {1: OFFICIAL})[0]
    assert out["origen"] == ORIGEN_INFERIDO


def test_unit_period_metric_mismatch_or_not_reported_is_inferido():
    for patch in (
        {"unit": "EUR"},
        {"period": "FY2024"},
        {"metric": "net_income"},
        {"is_reported": False},
    ):
        out = classify_origin([_item("revenue", "dato", [1])], {1: {**OFFICIAL, **patch}})[0]
        assert out["origen"] == ORIGEN_INFERIDO, patch


def test_override_policy_llm_with_label_dato_is_inferido():
    for st in ("assumption_override", "model_policy", "llm_estimate", "user_provided"):
        out = classify_origin([_item("revenue", "dato", [1], st, value=1.0)], {1: OFFICIAL})[0]
        assert out["origen"] == ORIGEN_INFERIDO, st


def test_legacy_item_without_origin_fields_is_inferido():
    legacy = {"key": "wacc", "label": "dato", "value": 1.0, "source_fact_ids": [1]}
    out = classify_origin([legacy], {1: OFFICIAL})[0]
    assert out["origen"] == ORIGEN_INFERIDO


def test_latest_inputs_provenance_resolves_sources_from_persisted_documents():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(ticker="TST", name="Test", exchange="NASDAQ", company_type="growth", valuation_model="unassigned")
        db.add(company)
        db.flush()
        doc = Document(
            company_id=company.id,
            title="10-Q",
            source_type="primary_official",
            source_url=SEC,
            published_at=datetime(2026, 8, 10, tzinfo=UTC),
        )
        db.add(doc)
        db.flush()
        fact = FinancialFact(
            company_id=company.id,
            metric="revenue",
            value=Decimal("5"),
            unit="USD",
            period="FY2025",
            source_id=doc.id,
            source_type="sec",
        )
        db.add(fact)
        db.flush()
        snapshot = {
            "driver_model": [
                {
                    "key": "revenue",
                    "status": "sourced",
                    "value": 5,
                    "driver_type": "kpi",
                    "unit": "USD",
                    "source_fact_ids": [fact.id],
                    "confidence": 0.9,
                    "trace": {"period": "FY2025"},
                },
                {
                    "key": "revenue_wrong_value",
                    "status": "sourced",
                    "value": 999,
                    "unit": "USD",
                    "driver_type": "kpi",
                    "source_fact_ids": [fact.id],
                    "confidence": 0.9,
                    "trace": {"period": "FY2025"},
                },
            ],
            # Un id declarado que no existe en la BD no puede ser OFICIAL.
            "assumptions": {
                "ghost": {
                    "value": 1,
                    "source_type": "financial_facts",
                    "basis": "b",
                    "source_fact_ids": [99999],
                    "confidence": 0.5,
                }
            },
        }
        db.add(
            FundamentalModelVersion(
                company_id=company.id, version=1, engine_version="e1", algorithm_version="a1", framework_key="space_network", horizon_years=5, status="ok", publishable=True, input_fingerprint="a" * 64, forecast_fingerprint="a" * 64, market_snapshot_fingerprint="a" * 64, valuation_snapshot_fingerprint="a" * 64, model_snapshot=snapshot
            )
        )
        db.commit()
        by_key = {i["key"]: i for i in latest_inputs_provenance(db, company.id)}
    assert by_key["revenue"]["origen"] == ORIGEN_OFICIAL
    assert by_key["revenue"]["fuentes"][0]["url"] == SEC
    assert by_key["ghost"]["origen"] == ORIGEN_INFERIDO
    assert by_key["revenue_wrong_value"]["origen"] == ORIGEN_INFERIDO

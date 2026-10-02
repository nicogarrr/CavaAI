from decimal import Decimal

from sqlalchemy import delete, select

from app.core.database import SessionLocal, init_db
from app.models import Company, FinancialFact
from app.services.valuation_service import ValuationService


def test_sotp_requires_sourced_segment_metrics_multiples_and_discount():
    init_db()
    db = SessionLocal()
    company_id: int | None = None
    ticker = "SOTPE"
    try:
        existing = db.scalar(select(Company).where(Company.ticker == ticker))
        if existing:
            db.execute(delete(FinancialFact).where(FinancialFact.company_id == existing.id))
            db.delete(existing)
            db.commit()

        company = Company(
            ticker=ticker,
            name="SOTP evidence test",
            exchange="TEST",
            currency="USD",
            sector="Industrials",
            industry="Conglomerate",
            company_type="multi_segment",
            valuation_model="sotp",
            special_sources=[],
            special_risks=[],
            factor_tags=["sotp"],
        )
        db.add(company)
        db.flush()
        company_id = company.id
        facts = {
            "shares_diluted": 100,
            "net_debt": 250,
            "holding_company_discount": 0.12,
            "segment_services_operating_metric": 80,
            "segment_services_valuation_multiple": 12,
            "segment_assets_operating_metric": 500,
            "segment_assets_valuation_multiple": 1.1,
        }
        for metric, value in facts.items():
            db.add(
                FinancialFact(
                    company_id=company.id,
                    metric=metric,
                    value=Decimal(str(value)),
                    unit="decimal",
                    period="FY2025",
                    fiscal_year=2025,
                    fiscal_quarter="FY",
                    source_type="sotp_engine_test",
                    confidence=Decimal("0.91"),
                )
            )
        db.commit()

        result = ValuationService().value_company(db, company)
        probabilities = [
            result["trace"]["scenarios"][name]["definition"]["probability"]
            for name in ("bear", "base", "bull")
        ]

        assert result["status"] == "ok"
        assert result["publishable"] is True
        assert result["trace"]["holding_discount_source"] == "financial_facts"
        assert "segment_services_valuation_multiple" in result["trace"]["fact_ids"]
        assert probabilities != [0.25, 0.50, 0.25]
        assert abs(sum(probabilities) - 1.0) < 1e-9
    finally:
        if company_id is not None:
            db.execute(delete(FinancialFact).where(FinancialFact.company_id == company_id))
            db.execute(delete(Company).where(Company.id == company_id))
            db.commit()
        db.close()


BASE_FACTS = {
    "shares_diluted": 100,
    "net_debt": 250,
    "holding_company_discount": 0.12,
    "segment_services_operating_metric": 80,
    "segment_services_valuation_multiple": 12,
    "segment_assets_operating_metric": 500,
    "segment_assets_valuation_multiple": 1.1,
}


def _sotp_result(facts_overrides: dict) -> dict:
    """Valida SOTPE con `facts_overrides` aplicando encima de BASE_FACTS.

    `None` como valor borra el fact: es la forma de expresar "no existe".
    """
    init_db()
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.ticker == "SOTPE"))
        if company:
            db.execute(delete(FinancialFact).where(FinancialFact.company_id == company.id))
            db.delete(company)
            db.commit()
        company = Company(
            ticker="SOTPE",
            name="SOTP evidence test",
            exchange="TEST",
            currency="USD",
            sector="Industrials",
            industry="Conglomerate",
            company_type="multi_segment",
            valuation_model="sotp",
            factor_tags=["sotp"],
        )
        db.add(company)
        db.flush()
        for metric, value in {**BASE_FACTS, **facts_overrides}.items():
            if value is None:
                continue
            db.add(
                FinancialFact(
                    company_id=company.id,
                    metric=metric,
                    value=Decimal(str(value)),
                    unit="decimal",
                    period="FY2025",
                    fiscal_year=2025,
                    fiscal_quarter="FY",
                    source_type="sotp_engine_test",
                    confidence=Decimal("0.91"),
                )
            )
        db.commit()
        return ValuationService().value_company(db, company)
    finally:
        db.execute(delete(FinancialFact).where(FinancialFact.company_id == company.id))
        db.execute(delete(Company).where(Company.id == company.id))
        db.commit()
        db.close()


def test_every_blocking_input_is_named_in_missing_inputs():
    """Cada condicion que bloquea tiene que DECIRSE en `missing_inputs`.

    El motor decidia con `missing or not segments or shares is None or
    shares <= 0 or net_debt is None`: los disjuntos repetidos no anadian
    cobertura (todo lo que bloqueaba ya estaba en la lista) y hacia
    imposible saber que habia bloqueado leyendo el motivo. Este test ata una
    etiqueta por condicion.
    """
    # Shares ausentes.
    result = _sotp_result({"shares_diluted": None})
    assert result["status"] == "insufficient_data"
    assert result["missing_inputs"] == ["shares_diluted"]

    # Shares inutilizables (cero o negativo): tampoco son acciones.
    result = _sotp_result({"shares_diluted": 0})
    assert result["status"] == "insufficient_data"
    assert result["missing_inputs"] == ["shares_diluted"]

    # Deuda neta ausente: el NAV no se puede cerrar.
    result = _sotp_result({"net_debt": None})
    assert result["status"] == "insufficient_data"
    assert result["missing_inputs"] == ["net_debt"]

    # Descuento fuera de [0, 1): no es un descuento de holding.
    result = _sotp_result({"holding_company_discount": 1.4})
    assert result["status"] == "insufficient_data"
    assert result["missing_inputs"] == ["holding_company_discount"]

    # Ningun segmento valorable.
    result = _sotp_result(
        {
            "segment_services_operating_metric": None,
            "segment_services_valuation_multiple": None,
            "segment_assets_operating_metric": None,
            "segment_assets_valuation_multiple": None,
        }
    )
    assert result["status"] == "insufficient_data"
    assert result["missing_inputs"] == [
        "segment_*_operating_metric",
        "segment_*_valuation_multiple",
    ]
    assert result["trace"]["segment_fact_contract"]["operating_metric"] == (
        "segment_{name}_operating_metric"
    )

    # Completo: ninguna de esas condiciones aparece como bloqueo.
    result = _sotp_result({})
    assert result["status"] == "ok"
    assert result["publishable"] is True


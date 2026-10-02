"""Empresa sin ingresos reportados: un unico motivo honesto, sin listar como
faltantes datos que si existen (acciones diluidas, ano fiscal)."""

from decimal import Decimal

from sqlalchemy import delete, select

from app.core.database import SessionLocal, init_db
from app.models import Company, FinancialFact
from app.services.long_term_model_service import LongTermModelService

TICKER = "PRVX"


def _cleanup() -> None:
    init_db()
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.ticker == TICKER))
        if company:
            db.execute(delete(FinancialFact).where(FinancialFact.company_id == company.id))
            db.delete(company)
            db.commit()
    finally:
        db.close()


def _fact(db, company, metric, value, year, unit="USD"):
    db.add(
        FinancialFact(
            company_id=company.id,
            metric=metric,
            value=Decimal(str(value)),
            unit=unit,
            period=f"{year}-12-31:FY",
            fiscal_year=year,
            fiscal_quarter="FY",
            source_type="SEC",
            is_reported=True,
            confidence=Decimal("0.95"),
        )
    )


def test_pre_revenue_da_un_unico_motivo_y_no_marca_faltantes_los_datos_que_existen():
    _cleanup()
    db = SessionLocal()
    try:
        company = Company(
            ticker=TICKER, name="Pre Revenue Bio", exchange="TEST", currency="USD",
            sector="Health Care", industry="Biotechnology", company_type="standard",
            valuation_model="standard_dcf", special_sources=[], special_risks=[],
            factor_tags=[],
        )
        db.add(company)
        db.flush()
        for year in (2023, 2024, 2025):
            _fact(db, company, "net_income", -60_000_000, year)
            _fact(db, company, "free_cash_flow", -50_000_000, year)
            _fact(db, company, "shares_diluted", 126_000_000, year, unit="shares")
        db.commit()
        model = LongTermModelService().build(db, company)
        missing = model["missing_inputs"]
        assert missing[0] == "no_revenue_reported"
        assert "shares_diluted" not in missing
        assert "fiscal_year" not in missing
        assert model["publishable"] is False
    finally:
        db.close()
        _cleanup()


def test_pre_revenue_sin_acciones_las_sigue_marcando_faltantes():
    _cleanup()
    db = SessionLocal()
    try:
        company = Company(
            ticker=TICKER, name="Pre Revenue Bio", exchange="TEST", currency="USD",
            sector="Health Care", industry="Biotechnology", company_type="standard",
            valuation_model="standard_dcf", special_sources=[], special_risks=[],
            factor_tags=[],
        )
        db.add(company)
        db.flush()
        _fact(db, company, "net_income", -60_000_000, 2025)
        db.commit()
        model = LongTermModelService().build(db, company)
        assert model["missing_inputs"][:2] == ["no_revenue_reported", "shares_diluted"]
    finally:
        db.close()
        _cleanup()

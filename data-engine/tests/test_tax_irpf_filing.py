"""Capa IRPF (casillas Modelo 100 + deducción por doble imposición).

Verificado contra fuentes oficiales:
- Diseño de casillas: anexo del Modelo 100 en la Orden HAC/277/2026
  (BOE-A-2026-7041): 0327 denominación, 0328 transmisión global, 0331
  adquisición global, 0336/0338 resultados, 0339/0340 sumas; 0029
  dividendos; 0588 doble imposición internacional; 0597 retenciones por
  rendimientos del capital mobiliario.
- Escala del ahorro 2025: Ley 7/2024 (19/21/23/27/30; sede AEAT,
  "Principales novedades Ley 7/2024").

Hermético: SQLite en memoria, sin red.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, FXRate, Portfolio, Transaction
from app.services.tax_irpf_filing import (
    CASILLAS_BASIS,
    build_casillas,
    build_double_taxation,
    calculate_savings_tax,
)
from app.services.tax_report_service import TaxReportService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _eur_portfolio(db: Session) -> None:
    db.add(Portfolio(name="Main", base_currency="EUR", is_default=True))
    db.commit()


def _company(db: Session, ticker: str, country: str | None = None) -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[],
        factor_tags=[], domicile_country=country,
    )
    db.add(company)
    db.commit()
    return company


def _fx(db: Session, quote: str, rate_date: date, rate: str) -> None:
    db.add(FXRate(
        base_currency="EUR", quote_currency=quote,
        rate=Decimal(rate), rate_date=rate_date, source="test",
    ))
    db.commit()


def _tx(db, company, day, action, qty, price, currency="USD", fees="0"):
    db.add(Transaction(
        company_id=company.id, trade_date=day, action=action,
        quantity=Decimal(str(qty)), price=Decimal(str(price)),
        fees=Decimal(str(fees)), currency=currency,
    ))
    db.commit()


# --- Escala del ahorro ------------------------------------------------------

def test_savings_tax_2025_brackets():
    # 19% primeros 6.000 + 21% hasta 50.000: 6.000*0.19 + 4.000*0.21
    assert calculate_savings_tax(Decimal("10000"), 2025) == Decimal("1980.00")
    # Tramo >300.000 al 30% (Ley 7/2024), no 28%:
    # 1.140 + 9.240 + 34.500 + 27.000 + 100.000*0.30 = 101.880
    assert calculate_savings_tax(Decimal("400000"), 2025) == Decimal("101880.00")


def test_savings_tax_historical_scales():
    # 2023-2024: tramo >300.000 al 28%
    assert calculate_savings_tax(Decimal("400000"), 2024) == Decimal("99880.00")
    # 2021-2022: 19/21/23/26
    assert calculate_savings_tax(Decimal("400000"), 2022) == Decimal("96880.00")


def test_savings_tax_zero_or_negative():
    assert calculate_savings_tax(Decimal("0"), 2025) == Decimal("0")
    assert calculate_savings_tax(Decimal("-100"), 2025) == Decimal("0")


# --- Casillas Modelo 100 ----------------------------------------------------

def _sale(ticker, date_s, proceeds, cost, gain):
    return {
        "ticker": ticker,
        "currency": "USD",
        "sales": [{
            "date": date_s,
            "proceeds_base": proceeds,
            "cost_base": cost,
            "gain_base": gain,
        }],
    }


def test_casillas_gains_losses_split():
    realized = [
        _sale("WIN", "2025-03-01", 1500.0, 1000.0, 500.0),
        _sale("LOSE", "2025-04-01", 600.0, 1000.0, -400.0),
    ]
    casillas = build_casillas([], realized, 2025)
    block = casillas["acciones_negociadas"]
    assert casillas["available"] is True
    assert casillas["basis"] == CASILLAS_BASIS
    assert block["0328_transmision_global"] == 2100.0
    assert block["0331_adquisicion_global"] == 2000.0
    assert block["0339_suma_ganancias"] == 500.0
    assert block["0340_suma_perdidas"] == 400.0
    assert block["incomplete"] is False
    assert len(block["rows"]) == 2


def test_casillas_missing_fx_marks_incomplete_and_nulls_totals():
    realized = [_sale("NOFX", "2025-03-01", None, None, None)]
    casillas = build_casillas([], realized, 2025)
    block = casillas["acciones_negociadas"]
    assert block["incomplete"] is True
    assert block["0328_transmision_global"] is None
    assert block["0339_suma_ganancias"] is None
    # La fila sigue visible con Nones honestos.
    assert block["rows"][0]["gain_base"] is None


def test_casillas_unavailable_for_unverified_year():
    casillas = build_casillas([], [], 2024)
    assert casillas["available"] is False
    assert "2025" in casillas["unavailable_reason"]


def test_casillas_dividends_box_0029():
    dividends = [{
        "ticker": "AAPL", "dividends_base": 90.0, "withholding_base": 13.5,
        "missing_fx": False,
    }]
    casillas = build_casillas(dividends, [], 2025)
    assert casillas["dividendos"]["0029_ingresos_integros"] == 90.0


# --- Doble imposición (art. 80 LIRPF, casilla 0588) --------------------------

def test_double_taxation_us_treaty_cap_15pct():
    # Retenido 30% (sin W-8BEN): tope de convenio 15%, exceso reclamable en
    # origen. Sin TME de la declaración completa la deducción NO se publica.
    dividends = [{
        "ticker": "AAPL", "dividends_base": 100.0, "withholding_base": 30.0,
        "missing_fx": False, "payments": [],
    }]
    result = build_double_taxation(dividends, {"AAPL": "US"}, 2025)
    us = result["countries"][0]
    assert us["treaty_cap_base"] == 15.0            # tope convenio
    assert us["excess_reclaimable_base"] == 15.0    # a reclamar en origen
    assert us["deduction_base"] is None
    assert us["status"] == "pendiente_tme"
    assert us["treaty_rate_source"].startswith("BOE-A-1990-30940")
    assert result["excess_withholding_reclaimable"] is True
    assert result["total_deduction_base"] is None
    assert result["status"] == "pendiente_tme"


def test_double_taxation_with_manual_tme_computes_deduction():
    # Con TME del borrador (entrada manual): deducción = min(tope, bruto×TME).
    dividends = [{
        "ticker": "MSFT", "dividends_base": 100.0, "withholding_base": 15.0,
        "missing_fx": False, "payments": [],
    }]
    # TME 19%: cuota española 19 > tope 15 → deducción = 15
    result = build_double_taxation(dividends, {"MSFT": "US"}, 2025, tme=Decimal("0.19"))
    assert result["countries"][0]["deduction_base"] == 15.0
    assert result["total_deduction_base"] == 15.0
    assert result["status"] == "calculada_con_tme_manual"
    assert result["partial"] is False
    # TME 10%: cuota española 10 < tope 15 → deducción = 10
    result = build_double_taxation(dividends, {"MSFT": "US"}, 2025, tme=Decimal("0.10"))
    assert result["countries"][0]["deduction_base"] == 10.0


def test_double_taxation_country_without_verified_treaty_is_manual_review():
    dividends = [{
        "ticker": "ASML", "dividends_base": 100.0, "withholding_base": 15.0,
        "missing_fx": False, "payments": [],
    }]
    result = build_double_taxation(dividends, {"ASML": "NL"}, 2025)
    assert result["countries"] == []
    assert result["manual_review"][0]["ticker"] == "ASML"
    assert "convenio" in result["manual_review"][0]["reason"]
    assert result["partial"] is True
    assert result["total_deduction_base"] is None


def test_double_taxation_special_payment_types_are_manual_review():
    dividends = [{
        "ticker": "XYZ", "dividends_base": 50.0, "withholding_base": 7.5,
        "missing_fx": False,
        "payments": [
            {"type": "dividend", "raw_action": "Payment In Lieu Of Dividends",
             "date": "2025-03-01", "amount_native": 50.0, "amount_base": 50.0},
        ],
    }]
    result = build_double_taxation(dividends, {"XYZ": "US"}, 2025)
    assert result["countries"] == []
    assert result["manual_review"][0]["ticker"] == "XYZ"
    assert "especial" in result["manual_review"][0]["reason"]
    assert result["partial"] is True


def test_double_taxation_spanish_withholding_goes_to_0597_not_0588():
    dividends = [{
        "ticker": "IBE", "dividends_base": 100.0, "withholding_base": 19.0,
        "missing_fx": False, "payments": [],
    }]
    result = build_double_taxation(dividends, {"IBE": "ES"}, 2025)
    assert result["countries"] == []                 # ES nunca es crédito 0588
    assert result["total_deduction_base"] is None    # sin TME no hay total
    assert result["spanish_withholding_base"]["casilla"] == "0597"
    assert result["spanish_withholding_base"]["amount"] == 19.0


def test_double_taxation_unknown_country_is_manual_review():
    dividends = [{
        "ticker": "XYZ", "dividends_base": 50.0, "withholding_base": 7.5,
        "missing_fx": False, "payments": [],
    }]
    result = build_double_taxation(dividends, {}, 2025)   # sin domicilio
    assert result["total_deduction_base"] is None
    assert result["manual_review"][0]["ticker"] == "XYZ"
    assert "desconocido" in result["manual_review"][0]["reason"]
    assert result["partial"] is True


def test_double_taxation_missing_fx_is_manual_review():
    dividends = [{
        "ticker": "NOFX", "dividends_base": None, "withholding_base": None,
        "missing_fx": True, "payments": [],
    }]
    result = build_double_taxation(dividends, {"NOFX": "US"}, 2025)
    assert result["manual_review"][0]["ticker"] == "NOFX"
    assert result["total_deduction_base"] is None
    assert result["partial"] is True


# --- Integración con el informe ---------------------------------------------

def test_compute_report_attaches_filing_layer(db):
    _eur_portfolio(db)
    aapl = _company(db, "AAPL", country="US")
    pay_day = date(2025, 5, 15)
    _fx(db, "USD", pay_day, "0.90")
    _tx(db, aapl, pay_day, "dividend", 0, 100)     # bruto 100 USD
    _tx(db, aapl, pay_day, "withholding", 0, 15)   # retención 15 USD
    _tx(db, aapl, date(2025, 1, 10), "buy", 10, 100, currency="EUR")
    _tx(db, aapl, date(2025, 6, 1), "sell", 10, 150, currency="EUR")  # +500 EUR

    report = TaxReportService().compute_report(db, 2025)
    filing = report["filing"]
    casillas = filing["casillas"]
    assert casillas["available"] is True
    assert casillas["basis"] == "orden-hac-277-2026-renta-2025"
    block = casillas["acciones_negociadas"]
    assert block["0328_transmision_global"] == 1500.0
    assert block["0331_adquisicion_global"] == 1000.0
    assert block["0339_suma_ganancias"] == 500.0
    assert block["0340_suma_perdidas"] == 0.0
    assert casillas["dividendos"]["0029_ingresos_integros"] == pytest.approx(90.0)

    dt = filing["double_taxation"]
    assert dt["casilla"] == "0588"
    assert dt["countries"][0]["country"] == "US"
    # Sin TME del borrador no hay deducción publicada: solo el tope de
    # convenio (13,5 retenidos < 15% de 90 = 13,5 → tope = retenido).
    assert dt["countries"][0]["treaty_cap_base"] == pytest.approx(13.5)
    assert dt["countries"][0]["deduction_base"] is None
    assert dt["status"] == "pendiente_tme"
    assert dt["total_deduction_base"] is None
    assert filing["available"] is True


def test_filing_unavailable_when_portfolio_base_is_not_eur(db):
    # Las casillas del Modelo 100 son importes en EUR: con cartera en USD no
    # se publican cifras bajo rótulos IRPF.
    db.add(Portfolio(name="Main", base_currency="USD", is_default=True))
    db.commit()
    c = _company(db, "AAPL", country="US")
    _tx(db, c, date(2025, 1, 10), "buy", 10, 100, currency="USD")
    _tx(db, c, date(2025, 6, 1), "sell", 10, 150, currency="USD")

    report = TaxReportService().compute_report(db, 2025)
    assert report["summary"]["base_currency"] == "USD"
    filing = report["filing"]
    assert filing["available"] is False
    assert "EUR" in filing["reason"]

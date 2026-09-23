"""Fuentes gratuitas sin datos inventados.

Cubre las correcciones de la auditoría de datos fabricados:
- Cadena Finnhub -> EDGAR -> Yahoo con fallo aislado y errores honestos (FMP
  eliminado: su key estaba muerta).
- registry de engines sin tickers mágicos: la decisión vive en company_master.
- claim_intelligence: confidence/materiality derivados de reglas (nunca
  constantes redondas) y marcado confidence_source="heuristic".
- news: la confianza del ExternalClaim deriva de la regla de fiabilidad de
  fuente (SOURCE_TIERS), no de un 0.65 inventado.

Tests herméticos: proveedores inyectables por constructor, sin red.
"""

import asyncio
import inspect
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, EvidenceSuggestion, ExternalClaim, FinancialFact, MarketPrice
from app.services.claim_intelligence_service import (
    ClaimIntelligenceService,
    _rule_scores,
    heuristic_statement,
)
from app.services.financial_ingestion_service import FinancialIngestionService
from app.services.news_service import NewsService
from app.services.source_hierarchy_service import classify_source
from app.valuation.engines.registry import resolve_engine_key


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, ticker: str = "AAA", **overrides) -> Company:
    fields = dict(
        ticker=ticker,
        name=ticker,
        exchange="NASDAQ",
        currency="USD",
        sector="S",
        industry="I",
        company_type="tech",
        valuation_model="standard_dcf+x",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    fields.update(overrides)
    company = Company(**fields)
    db.add(company)
    db.commit()
    return company


# --------------------------------------------------------------------------
# (4) registry: sin tickers mágicos, decisión en company_master
# --------------------------------------------------------------------------

def test_engine_registry_sin_tickers_magicos_y_dirigido_por_master():
    import app.valuation.engines.registry as registry_module

    source = inspect.getsource(registry_module)
    assert '"BN"' not in source and '"BABA"' not in source and '"RKLB"' not in source
    assert "company.ticker" not in source, "el engine jamás se decide por ticker"

    from app.data.company_master import COMPANY_MASTER

    master = {row["ticker"]: row for row in COMPANY_MASTER}
    expected = {"BN": "holding_company", "BABA": "holding_company", "RKLB": "sotp"}
    for ticker, engine_key in expected.items():
        row = master[ticker]
        # Con un ticker ajeno: la decisión viene de valuation_model/factor_tags.
        company = Company(
            ticker="ZZZ",
            name="x",
            exchange="NYSE",
            currency="USD",
            sector="x",
            industry="x",
            company_type=row["company_type"],
            valuation_model=row["valuation_model"],
            special_sources=[],
            special_risks=[],
            factor_tags=list(row["factor_tags"]),
        )
        assert resolve_engine_key(company) == engine_key, ticker
        company.ticker = ticker
        assert resolve_engine_key(company) == engine_key, ticker


# --------------------------------------------------------------------------
# (5) cadena Finnhub -> EDGAR -> Yahoo: fallback con errores honestos
# --------------------------------------------------------------------------

class OkFinnhub:
    name = "finnhub"

    def configured(self) -> bool:
        return True

    async def profile(self, ticker: str):
        return {"marketCapitalization": 2_000_000}

    async def quote(self, ticker: str):
        return {"c": 21.5, "t": 1704153600}


class BrokenSEC:
    async def cik_for_ticker(self, ticker: str):
        raise RuntimeError("SEC down")


class OkYahoo:
    name = "yahoo"

    async def quote(self, ticker: str):
        return {"regularMarketPrice": 22.0, "regularMarketTime": 1704153600}


class Broken:
    name = "broken"

    def configured(self) -> bool:
        return False

    async def quote(self, ticker: str):
        raise RuntimeError("down")

    async def profile(self, ticker: str):
        raise RuntimeError("down")


def test_chain_financials_finnhub_edgar_yahoo_con_errores_reportados(db):
    company = _company(db)
    result = asyncio.run(
        FinancialIngestionService().refresh_financials(
            db, company, finnhub=OkFinnhub(), sec_client=BrokenSEC(), yahoo=OkYahoo()
        )
    )
    assert result["provider"] == "Finnhub+Yahoo"
    assert any(err.startswith("EDGAR:") for err in result.get("errors", []))

    facts = db.scalars(select(FinancialFact)).all()
    metrics = {fact.metric for fact in facts}
    assert "market_cap" in metrics and "close_price" in metrics
    # Toda fila declara su proveedor real: nunca FMP ni una etiqueta inventada.
    assert {fact.source_type for fact in facts} <= {"Finnhub", "Yahoo", "derived"}
    prices = db.scalars(select(MarketPrice)).all()
    assert prices and prices[0].source in {"Finnhub", "Yahoo"}

    # Sin estados financieros no hay FCF derivado: el input de valuation NO
    # está listo (honesto: no se fabrica readiness).
    assert result["valuation_input_ready"] is False


def test_chain_sin_ninguna_fuente_no_fabrica_ingesta(db):
    company = _company(db)
    with pytest.raises(RuntimeError):
        asyncio.run(
            FinancialIngestionService().refresh_financials(
                db, company, finnhub=Broken(), sec_client=BrokenSEC(), yahoo=Broken()
            )
        )
    assert db.scalars(select(FinancialFact)).all() == []
    assert db.scalars(select(MarketPrice)).all() == []


# --------------------------------------------------------------------------
# (3) claim_intelligence: confidence/materiality por reglas, marcado heuristic
# --------------------------------------------------------------------------

def test_claim_fallback_scores_por_reglas_nunca_constantes(db):
    text = "AAPL raises buyback by 10%"  # <35 chars: sin frase extraíble
    statement = heuristic_statement(text)
    confidence, score = _rule_scores(text)
    assert statement.confidence == confidence
    assert statement.materiality_score == score
    # Nunca el par inventado (0.55, 5) salvo que la regla lo produzca.
    assert (round(statement.confidence, 4), statement.materiality_score) != (0.55, 5)

    rich = heuristic_statement(
        "Revenue growth record and a buyback of 5 billion expects guidance raise"
    )
    poor = heuristic_statement("something plain without numbers or markers at all")
    assert rich.materiality_score > poor.materiality_score
    assert rich.confidence > 0.52

    company = _company(db)
    service = ClaimIntelligenceService()
    result = service.scan_text(db, company=company, text=text, source_type="manual")
    assert result["suggestions"] >= 1
    row = db.scalars(select(EvidenceSuggestion)).all()[-1]
    assert row.metadata_.get("confidence_source") == "heuristic"
    assert float(row.confidence) == pytest.approx(statement.confidence)


# --------------------------------------------------------------------------
# (3) news: confianza del claim derivada de la regla de fiabilidad de fuente
# --------------------------------------------------------------------------

def test_manual_news_claim_confidence_deriva_de_regla_de_fuente(db):
    company = _company(db, ticker="AAPL", name="AAPL Co")
    service = NewsService()
    text = "AAPL beats revenue expectations with record margins in 2025 and guides higher."
    service.analyze_manual_news(db, text, "manual", None)

    claim = db.scalars(
        select(ExternalClaim).where(ExternalClaim.claim_type == "manual_news_claim")
    ).all()[-1]
    expected = round(classify_source("manual", None).trust_score, 4)
    assert float(claim.confidence) == pytest.approx(expected, abs=5e-5)
    assert float(claim.confidence) != 0.65
    assert claim.used_in_model is False

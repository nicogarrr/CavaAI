"""El asistente global (scope=portfolio, sin ticker) debe reconocer una empresa
nombrada por su ticker, también en minúsculas ("meta tesis?"), sin confundir
palabras corrientes con tickers."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company
from app.services.chat_service import ChatService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        for ticker, name in [
            ("META", "Meta Platforms"),
            ("NOW", "ServiceNow"),
            ("AMD", "AMD"),
            ("MSFT", "Microsoft"),
            ("BN", "Brookfield"),
        ]:
            session.add(
                Company(
                    ticker=ticker,
                    name=name,
                    exchange="NASDAQ",
                    currency="USD",
                    sector="Tech",
                    industry="Tech",
                    company_type="holding",
                    valuation_model="unassigned",
                    special_sources=[],
                    special_risks=[],
                    factor_tags=[],
                )
            )
        session.commit()
        yield session


def _resolve(db, question, scope="portfolio", ticker=None):
    company = ChatService()._resolve_company(db, question, scope, ticker)
    return company.ticker if company else None


@pytest.mark.parametrize(
    "question",
    [
        "meta tesis?",
        "Meta tesis",
        "tesis de meta",
        "¿qué opinas de META?",
        "analiza meta",
        "precio de META",
        "dame la ficha de meta",
    ],
)
def test_meta_se_reconoce_como_ticker(db, question):
    assert _resolve(db, question) == "META"


@pytest.mark.parametrize(
    "question",
    [
        "mi meta de ahorro este año",
        "cuál es mi meta",
        "la meta es ganar dinero",
        "meta?",
        "qué es el PER",
        "hola",
        "cómo va mi cartera",
        "now",
    ],
)
def test_palabras_corrientes_y_cartera_no_son_ticker(db, question):
    assert _resolve(db, question) is None


def test_ticker_en_minusculas_normal_vale(db):
    assert _resolve(db, "qué tal amd?") == "AMD"
    assert _resolve(db, "tesis de msft") == "MSFT"


def test_dos_empresas_no_se_adivinan(db):
    assert _resolve(db, "compara META y MSFT") is None


def test_ticker_corto_en_minusculas_no_cuenta_pero_en_mayusculas_si(db):
    assert _resolve(db, "tesis de bn") is None
    assert _resolve(db, "tesis de BN") == "BN"


def test_servicenow_en_mayusculas_o_con_pista(db):
    assert _resolve(db, "tesis de NOW") == "NOW"
    assert _resolve(db, "análisis de now") == "NOW"


def test_scope_company_o_ticker_explicito_sigue_igual(db):
    assert _resolve(db, "lo que sea", scope="company", ticker="MSFT") == "MSFT"
    assert _resolve(db, "precio de AMD", scope="company") == "AMD"


def test_flujo_completo_meta_tesis_ya_no_pide_ticker_con_llm_caido(db):
    import asyncio

    class Caido:
        name = "caido"

        async def complete(self, request):
            raise RuntimeError("proveedor caido")

    response = asyncio.run(ChatService(Caido()).answer(db, "meta tesis?", "portfolio", None, use_jev=False))
    assert "dame un ticker" not in response.answer
    assert "META" in response.answer or "Meta" in response.answer

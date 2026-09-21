"""Jev en alertas e ingesta: hermético con MockTransport (sin red, sin key real).

Cubre:
- Triage de alertas: 1 llamada Jev por alerta DISPARADA, 0 si no dispara.
- Fallback sin key: la alerta / el documento / la noticia se crean igual.
- Ingesta: `jev_doc_type` en metadata de Document y NewsEvent (1 llamada c/u).
- Telegram: la línea Jev solo aparece cuando hay score adjunto.
"""
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.llm.jev import JevDecisionClient
from app.models import Company, MarketPrice, NewsEvent, ResearchAlert
from app.schemas import NewsFeedItem
from app.services import jev_triage_service as jts
from app.services.alert_rule_service import AlertRuleService
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.news_service import NewsService
from app.services.notification_service import NotificationService


def _mock_jev(monkeypatch, calls: dict):
    """Jev falso sobre MockTransport: urgency->urgent, doc_type->earnings."""

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.content.decode())
        questions = body.get("questions") or {}
        answers = {}
        for name in questions:
            calls[name] = calls.get(name, 0) + 1
            if name == "doc_type":
                answers[name] = {
                    "type": "choice",
                    "choice": "earnings",
                    "confidence": 0.88,
                    "probabilities": {"earnings": 0.88, "filing": 0.05, "macro": 0.04, "opinion": 0.03},
                }
            else:
                answers[name] = {
                    "type": "choice",
                    "choice": "urgent",
                    "confidence": 0.91,
                    "probabilities": {"urgent": 0.91, "routine": 0.09},
                }
        return httpx.Response(
            200,
            json={"model": "jev-test", "answers": answers, "usage": {"input_tokens": 100}},
        )

    transport = httpx.MockTransport(handler)
    client = JevDecisionClient(api_key="test-key", client=httpx.AsyncClient(transport=transport))
    monkeypatch.setattr(jts, "build_client", lambda: client)
    return client


def _db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _company(db: Session, ticker: str) -> Company:
    company = Company(
        ticker=ticker,
        name=f"{ticker} Test",
        exchange="TEST",
        company_type="standard",
        valuation_model="dCF",
    )
    db.add(company)
    db.commit()
    return company


def _priced_company(db: Session, ticker: str, close: str) -> Company:
    company = _company(db, ticker)
    db.add(MarketPrice(company_id=company.id, date=date.today(), close=Decimal(close), source="test"))
    db.commit()
    return company


# --- (1) Triage de alertas ---------------------------------------------------

def test_alert_trigger_attaches_jev_urgency_once(monkeypatch):
    calls: dict = {}
    _mock_jev(monkeypatch, calls)
    engine = _db()
    with Session(engine) as db:
        company = _priced_company(db, "ALRT", "120")
        service = AlertRuleService()
        rule = service.create(db, company, rule_type="price_above", operator=">", value=100)
        result = service.evaluate(db, rule)

        assert result["status"] == "triggered"
        assert result["jev_urgency"]["label"] == "urgent"
        assert result["jev_urgency"]["confidence"] == pytest.approx(0.91)
        assert calls.get("urgency", 0) == 1  # 1 llamada por alerta disparada

        alert = db.scalar(select(ResearchAlert))
        assert alert is not None
        assert alert.metadata_["jev_urgency"]["label"] == "urgent"


def test_alert_not_triggered_makes_no_jev_call(monkeypatch):
    calls: dict = {}
    _mock_jev(monkeypatch, calls)
    engine = _db()
    with Session(engine) as db:
        company = _priced_company(db, "QUIET", "50")
        service = AlertRuleService()
        rule = service.create(db, company, rule_type="price_above", operator=">", value=100)
        result = service.evaluate(db, rule)

        assert result["status"] == "evaluated"
        assert result["jev_urgency"] is None
        assert calls == {}  # ninguna evaluación sin disparo llama a Jev


def test_alert_trigger_without_key_still_emits(monkeypatch):
    monkeypatch.setattr(jts, "build_client", lambda: None)
    engine = _db()
    with Session(engine) as db:
        company = _priced_company(db, "NOKEY", "120")
        service = AlertRuleService()
        rule = service.create(db, company, rule_type="price_above", operator=">", value=100)
        result = service.evaluate(db, rule)

        assert result["status"] == "triggered"
        assert result["jev_urgency"] is None
        alert = db.scalar(select(ResearchAlert))
        assert alert is not None
        assert "jev_urgency" not in (alert.metadata_ or {})


# --- (2) Clasificación en ingesta --------------------------------------------

def test_document_ingest_stores_jev_doc_type(monkeypatch, tmp_path):
    calls: dict = {}
    _mock_jev(monkeypatch, calls)
    monkeypatch.setenv("CAVAAI_ENABLE_AUTO_RESEARCH", "0")
    monkeypatch.setenv("CAVAAI_ENABLE_AUTO_KPI_EXTRACTION", "0")
    engine = _db()
    with Session(engine) as db:
        _company(db, "DOC")
        result = DocumentIngestionService().ingest_bytes(
            db,
            ticker="DOC",
            title="Q3 earnings note",
            content=(
                b"Q3 earnings: revenue grew 12% to $61.9B, EPS $2.90, "
                b"full-year guidance raised. Enough length for the parser."
            ),
            filename="q3-note.txt",
            source_type="test_jev",
        )
        assert result["status"] == "ingested"
        assert calls.get("doc_type", 0) == 1  # 1 llamada por documento

        from app.models import Document

        doc = db.scalar(select(Document).where(Document.checksum == result["checksum"]))
        assert doc.metadata_["jev_doc_type"]["label"] == "earnings"
        assert doc.metadata_["jev_doc_type"]["confidence"] == pytest.approx(0.88)


def test_document_ingest_without_key_skips_doc_type(monkeypatch):
    monkeypatch.setattr(jts, "build_client", lambda: None)
    monkeypatch.setenv("CAVAAI_ENABLE_AUTO_RESEARCH", "0")
    monkeypatch.setenv("CAVAAI_ENABLE_AUTO_KPI_EXTRACTION", "0")
    engine = _db()
    with Session(engine) as db:
        _company(db, "DOCNK")
        result = DocumentIngestionService().ingest_bytes(
            db,
            ticker="DOCNK",
            title="plain note",
            content=b"This is a plain business note with enough length here for parsing.",
            filename="note.txt",
            source_type="test_jev",
        )
        assert result["status"] == "ingested"
        from app.models import Document

        doc = db.scalar(select(Document).where(Document.checksum == result["checksum"]))
        assert "jev_doc_type" not in (doc.metadata_ or {})


def test_news_ingest_stores_jev_doc_type(monkeypatch):
    calls: dict = {}
    _mock_jev(monkeypatch, calls)
    engine = _db()
    with Session(engine) as db:
        response = NewsService().ingest_news_items(
            db,
            [
                NewsFeedItem(
                    title="Company beats Q3 estimates, raises guidance",
                    text="Revenue up 12%, EPS $2.90 vs $2.75 expected.",
                    ticker="ZZZ",
                    source="feed",
                )
            ],
            default_source="feed",
        )
        assert response.created == 1
        assert calls.get("doc_type", 0) == 1  # clasificación: 1 llamada
        news = db.scalar(select(NewsEvent))
        assert news is not None
        assert news.metadata_["jev_doc_type"]["label"] == "earnings"


# --- Telegram adjunta el score ------------------------------------------------

def test_telegram_text_includes_jev_line_when_present():
    text = NotificationService._telegram_text(
        {
            "severity": "high",
            "title": "ALRT rule matched",
            "message": "observed=120",
            "company_id": 1,
            "alert_id": 9,
            "jev_urgency": {"label": "urgent", "confidence": 0.91},
        }
    )
    assert "Jev urgency: urgent (conf 0.91)" in text


def test_telegram_text_omits_jev_line_without_score():
    text = NotificationService._telegram_text(
        {
            "severity": "high",
            "title": "ALRT rule matched",
            "message": "observed=120",
            "company_id": 1,
            "alert_id": 9,
            "jev_urgency": {},
        }
    )
    assert "Jev" not in text

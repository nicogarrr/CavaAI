from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import news as news_module
from app.core.database import get_db
from app.models.entities import Base, Company, NewsEvent, Tenant

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


def _company(ticker: str) -> Company:
    return Company(
        ticker=ticker,
        name=f"{ticker} Inc",
        exchange="NASDAQ",
        currency="USD",
        company_type="holding",
        valuation_model="unassigned",
    )


def test_news_events_filter_by_ticker():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as db:
        db.add(Tenant(id=1, external_id="t"))
        asts = _company("ASTS")
        rklb = _company("RKLB")
        db.add_all([asts, rklb])
        db.flush()
        db.add_all(
            [
                NewsEvent(
                    tenant_id=1, company_id=asts.id, title="asts news", source="rss",
                    url="https://publisher.example/1", date=NOW,
                    metadata_={"connector": "rss", "date_source": "source"},
                ),
                NewsEvent(
                    tenant_id=1, company_id=rklb.id, title="rklb news", source="rss",
                    url="https://publisher.example/2", date=NOW,
                    metadata_={"connector": "rss", "date_source": "source"},
                ),
                NewsEvent(
                    tenant_id=1, company_id=None, title="macro news", source="GDELT",
                    url="https://publisher.example/3", date=NOW,
                    metadata_={"connector": "gdelt", "news_lane": "macro"},
                ),
            ]
        )
        db.commit()

        app = FastAPI()
        app.include_router(news_module.router, prefix="/api/news")

        def _override_db():
            yield db

        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app)

        # Sin filtro: todo.
        response = client.get("/api/news")
        assert response.status_code == 200, response.text
        assert {row["title"] for row in response.json()} == {
            "asts news",
            "rklb news",
            "macro news",
        }

        # Con ticker (minusculas: normaliza a mayusculas): solo esa empresa.
        response = client.get("/api/news?ticker=asts")
        assert response.status_code == 200, response.text
        rows = response.json()
        assert {row["title"] for row in rows} == {"asts news"}
        assert rows[0]["ticker"] == "ASTS"

        # Ticker sin eventos: lista vacia, no error.
        response = client.get("/api/news?ticker=NVDA")
        assert response.status_code == 200, response.text
        assert response.json() == []
    engine.dispose()

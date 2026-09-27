"""Macro lane: specific theme queries, lane/theme provenance at creation, no company link."""

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, NewsEvent, Tenant
from app.schemas import NewsFeedItem
from app.services.macro_news import MACRO_GDELT_QUERIES, MACRO_NEWS_LANE, iter_macro_queries
from app.services.news_service import NewsService


def test_queries_are_specific_and_cover_approved_themes():
    themes = {theme for theme, _ in iter_macro_queries()}
    expected = {
        "gold_central_banks", "interest_rates", "commodities", "trucking_freight",
        "ai_investment", "hormuz_oil", "energy", "semiconductors", "dollar_fx",
        "inflation", "liquidity_m2", "china_supply_chains", "us_trade_policy",
    }
    assert themes == expected
    for theme, query in MACRO_GDELT_QUERIES:
        # específicas: al menos una frase entrecomillada o paréntesis con OR
        assert ('"' in query) or ("(" in query and " OR " in query), theme
        # ruido: ninguna consulta es un término genérico suelto
        assert query.strip().lower() not in {"gold", "oil", "ai", "china", "inflation"}, theme


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add_all([
        Tenant(id=1, external_id="one"),
        Company(id=1, ticker="GLD", name="Gold Corp", exchange="NYSE",
                currency="USD", company_type="holding", valuation_model="unassigned",
                special_sources=[], special_risks=[], factor_tags=[]),
    ])
    db.commit()
    db.info["tenant_id"] = 1
    return db


def test_macro_ingest_labels_lane_theme_and_skips_company_detection():
    db = _db()
    item = NewsFeedItem(
        title="GLD reserves jump as central banks buy gold",
        text="Central banks added gold above official figures, Goldman nowcast says.",
        ticker=None,
        url="https://example.test/macro-1",
        source="GDELT",
        published_at=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
    )
    response = NewsService().ingest_news_items(
        db, [item], default_source="gdelt", connector="gdelt",
        date_source_label="gdelt_first_seen",
        news_lane=MACRO_NEWS_LANE, macro_theme="gold_central_banks",
        detect_company=False,
    )
    assert response.created == 1
    event = db.query(NewsEvent).one()
    # sin vínculo a empresa aunque el titular empiece por un ticker real
    assert event.company_id is None
    metadata = event.metadata_
    assert metadata["news_lane"] == "macro"
    assert metadata["macro_theme"] == "gold_central_banks"
    # procedencia GDELT intacta en la transacción de creación
    assert metadata["connector"] == "gdelt"
    assert metadata["date_source"] == "gdelt_first_seen"
    assert metadata["source_headline"] == "GLD reserves jump as central banks buy gold"


def test_macro_ingest_dedupes_by_url():
    db = _db()
    item = NewsFeedItem(
        title="Oil slips as Hormuz tensions ease",
        text=None, ticker=None, url="https://example.test/macro-dup",
        source="GDELT", published_at=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
    )
    service = NewsService()
    kwargs = dict(default_source="gdelt", connector="gdelt",
                  date_source_label="gdelt_first_seen",
                  news_lane=MACRO_NEWS_LANE, macro_theme="hormuz_oil",
                  detect_company=False)
    assert service.ingest_news_items(db, [item], **kwargs).created == 1
    again = service.ingest_news_items(db, [item], **kwargs)
    assert again.created == 0 and again.skipped_duplicates == 1

"""Una fórmula de RANKING es un desempate, nunca un filtro de pertenencia.

El ranking ordena el resultado; no decide si una compañía entra en la pantalla.
Antes, `missing` era un único conjunto compartido entre criterios y ranking: una
compañía que cumplía TODOS los criterios pero le faltaba la métrica de ranking
salía `matched: false`, no contaba en `match_count`, nunca se convertía en
`SavedScreenMatch` y DESACTIVABA una coincidencia que ya existía — con lo que sus
alertas dejaban de dispararse en silencio.

La unión de campos que falten se conserva para la CALIDAD del resultado
(`missing_fields`, `coverage_percent`, `confidence`); `matched` sólo depende de
los criterios.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import (
    CalculatedMetric,
    Company,
    ResearchAlert,
    SavedScreenMatch,
    Tenant,
)
from app.services.screener_service import ScreenerService


def _company(ticker: str) -> Company:
    return Company(
        ticker=ticker,
        name=f"{ticker} Co",
        exchange="TEST",
        currency="USD",
        sector="Test",
        industry="Test",
        company_type="standard",
        valuation_model="standard_dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )


def _metric(db: Session, company: Company, metric: str, value: str) -> None:
    db.add(
        CalculatedMetric(
            company_id=company.id,
            metric=metric,
            value=Decimal(value),
            unit="decimal",
            period="FY2025",
            fiscal_year=2025,
            status="ok",
            definition_version="test-v1",
            formula=metric,
            source_fact_ids=[],
            calculation_trace={},
            confidence=Decimal("0.9"),
        )
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tenant = Tenant(external_id="ranking-vs-match", name="Ranking vs match")
        session.add(tenant)
        session.flush()
        session.info["tenant_id"] = tenant.id
        yield session


def _seed(db: Session) -> tuple[Company, Company]:
    """FULL cumple criterio + ranking. NORANK cumple el criterio pero no el ranking."""
    full = _company("FULL")
    norank = _company("NORANK")
    db.add_all([full, norank])
    db.flush()
    # Ambas superan roic > 0.1, el unico criterio de la pantalla.
    _metric(db, full, "roic", "0.25")
    _metric(db, norank, "roic", "0.18")
    # Solo FULL tiene la metrica de RANKING.
    _metric(db, full, "quality_score", "0.75")
    db.commit()
    return full, norank


def _screen(db: Session):
    return ScreenerService().create_screen(
        db,
        name="Quality",
        description="roic alto, ranking por quality_score",
        criteria=[{"left": "roic", "operator": ">", "right": "0.1"}],
        ranking_formula="quality_score",
        ranking_direction="desc",
        alerts_enabled=True,
    )


def test_company_missing_ranking_metric_is_still_matched(db: Session):
    full, norank = _seed(db)
    screen = _screen(db)

    response = ScreenerService().run(db, criteria=screen.criteria, ranking_formula="quality_score")

    norank_row = next(r for r in response["results"] if r["ticker"] == "NORANK")
    full_row = next(r for r in response["results"] if r["ticker"] == "FULL")

    # Pertenencia: la cumple porque cumple TODOS los criterios.
    assert norank_row["matched"] is True
    assert norank_row["criteria"][0]["passed"] is True
    # Ranking: solo desempata. Sin la metrica no hay rank_value, no "no coincide".
    assert norank_row["rank_value"] is None
    assert "ranking_status" not in norank_row
    # Calidad del resultado: la ausencia SIGUE siendo visible y honesta.
    assert norank_row["missing_fields"] == ["quality_score"]
    assert norank_row["coverage_percent"] == 50
    # Y sigue estando en la respuesta, ordenada detras de la que si tiene rank.
    assert full_row["matched"] is True
    assert response["results"][0]["ticker"] == "FULL"
    assert response["company_count"] == 2
    assert response["match_count"] == 2


def test_company_missing_ranking_metric_counts_and_creates_match_and_alert(db: Session):
    _full, norank = _seed(db)
    screen = _screen(db)

    response = ScreenerService().run_saved(db, screen)

    assert response["match_count"] == 2
    assert norank.id in response["new_match_company_ids"]
    match = db.scalar(
        select(SavedScreenMatch).where(
            SavedScreenMatch.saved_screen_id == screen.id,
            SavedScreenMatch.company_id == norank.id,
        )
    )
    assert match is not None
    assert match.active is True
    alerts = db.scalars(
        select(ResearchAlert).where(ResearchAlert.company_id == norank.id)
    ).all()
    assert [alert.alert_type for alert in alerts] == ["new_screen_match"]


def test_losing_the_ranking_metric_never_deactivates_an_existing_match(db: Session):
    """Elscenario silencioso del bug: el alert de una compañía deja de dispararse.

    NORANK empieza con la metrica de ranking, se convierte en coincidencia
    persistente y despacha su alerta. En la corrida siguiente pierde la metrica
    (una nueva ingesta todavia no la ha traido). La coincidencia debe SEGUIR
    activa: perder el desempate no es perder la pertenencia.
    """
    _full, norank = _seed(db)
    _metric(db, norank, "quality_score", "0.5")
    db.commit()
    screen = _screen(db)

    ScreenerService().run_saved(db, screen)
    match = db.scalar(
        select(SavedScreenMatch).where(
            SavedScreenMatch.saved_screen_id == screen.id,
            SavedScreenMatch.company_id == norank.id,
        )
    )
    assert match is not None and match.active is True

    # La metrica de ranking desaparece del universo para NORANK.
    for row in db.scalars(
        select(CalculatedMetric).where(
            CalculatedMetric.company_id == norank.id,
            CalculatedMetric.metric == "quality_score",
        )
    ).all():
        db.delete(row)
    db.commit()

    response = ScreenerService().run_saved(db, screen)

    db.refresh(match)
    assert response["match_count"] == 2
    assert match.active is True, (
        "perder la metrica de RANKING desactivo la coincidencia y detuvo su alerta"
    )
    # Sin cambio de pertenencia -> no hay "nueva" coincidencia ni alerta duplicada.
    assert norank.id not in response["new_match_company_ids"]

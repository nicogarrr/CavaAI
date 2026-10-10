from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.portfolio import portfolio_forecast
from app.core.database import Base
from app.models import (
    Company,
    FundamentalModelVersion,
    Position,
    Tenant,
    ThesisVersion,
)


def _tenant_session(engine) -> Session:
    db = Session(engine)
    tenant = db.query(Tenant).filter_by(external_id="forecast-test").first()
    if tenant is None:
        tenant = Tenant(external_id="forecast-test", name="Forecast test")
        db.add(tenant)
        db.flush()
    db.info["tenant_id"] = tenant.id
    return db


def _company(db: Session, ticker: str) -> Company:
    company = Company(ticker=ticker, name=f"{ticker} Inc", exchange="NASDAQ", company_type="operating_company", valuation_model="dcf")
    db.add(company)
    db.flush()
    return company


def _position(db: Session, company: Company, *, price: float, value: float) -> Position:
    position = Position(
        company_id=company.id,
        quantity=1,
        average_cost=price,
        market_price=price,
        market_value=value,
        market_value_base=value,
        currency="USD",
        base_currency="EUR",
        source="ibkr_flex",
        as_of=date(2026, 10, 9),
    )
    db.add(position)
    db.flush()
    return position


def _thesis(
    db: Session,
    company: Company,
    *,
    version: int,
    status: str,
    bear: float,
    base: float,
    bull: float,
    probs: dict | None = None,
) -> ThesisVersion:
    thesis = ThesisVersion(
        company_id=company.id,
        version=version,
        status=status,
        thesis_markdown="md",
        executive_summary="sum",
        bear_value=bear,
        base_value=base,
        bull_value=bull,
        scenario_probabilities=probs,
    )
    db.add(thesis)
    db.flush()
    return thesis


def _model(
    db: Session,
    company: Company,
    *,
    version: int,
    horizon: int,
    publishable: bool = True,
    probs: dict | None = None,
) -> FundamentalModelVersion:
    model = FundamentalModelVersion(
        company_id=company.id,
        version=version,
        engine_version="e1",
        algorithm_version="a1",
        framework_key="dcf",
        horizon_years=horizon,
        status="ok",
        publishable=publishable,
        input_fingerprint=f"in-{company.ticker}-{version}",
        forecast_fingerprint=f"fc-{company.ticker}-{version}",
        market_snapshot_fingerprint=f"ms-{company.ticker}-{version}",
        valuation_snapshot_fingerprint=f"vs-{company.ticker}-{version}",
        scenario_probabilities=probs or {},
    )
    db.add(model)
    db.flush()
    return model


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/forecast.db")
    Base.metadata.create_all(engine)
    with _tenant_session(engine) as db:
        yield db
    engine.dispose()


def test_forecast_weights_cagrs_and_exclusion(db_session):
    aaa = _company(db_session, "AAA")
    bbb = _company(db_session, "BBB")
    ccc = _company(db_session, "CCC")
    _position(db_session, aaa, price=100, value=7000)
    _position(db_session, bbb, price=50, value=2000)
    _position(db_session, ccc, price=10, value=1000)
    _thesis(
        db_session, aaa, version=1, status="published",
        bear=80, base=150, bull=200,
        probs={"bear": 0.2, "base": 0.6, "bull": 0.2},
    )
    _model(db_session, aaa, version=1, horizon=5)
    _thesis(db_session, bbb, version=1, status="published", bear=40, base=60, bull=90)
    _model(db_session, bbb, version=1, horizon=10)
    db_session.commit()

    result = portfolio_forecast(db=db_session)

    assert result["portfolio"]["total_value_base"] == 10000
    assert result["portfolio"]["covered_weight"] == pytest.approx(0.9)
    by_ticker = {item["ticker"]: item for item in result["positions"]}
    assert set(by_ticker) == {"AAA", "BBB"}
    assert by_ticker["AAA"]["weight"] == pytest.approx(0.7)
    assert by_ticker["AAA"]["cagr"]["base"] == pytest.approx(1.5 ** 0.2 - 1)
    assert by_ticker["AAA"]["total_return"]["bull"] == pytest.approx(1.0)
    expected_aaa = 0.2 * (0.8**0.2 - 1) + 0.6 * (1.5**0.2 - 1) + 0.2 * (2**0.2 - 1)
    assert by_ticker["AAA"]["expected_cagr"] == pytest.approx(expected_aaa)
    assert by_ticker["BBB"]["expected_cagr"] is None
    assert by_ticker["BBB"]["cagr"]["base"] == pytest.approx(1.2**0.1 - 1)
    portfolio_base = 0.7 * (1.5**0.2 - 1) + 0.2 * (1.2**0.1 - 1)
    assert result["portfolio"]["scenarios"]["base"]["cagr"] == pytest.approx(portfolio_base)
    assert result["portfolio"]["covered_only"]["scenarios"]["base"]["cagr"] == pytest.approx(
        portfolio_base / 0.9
    )
    assert result["portfolio"]["expected_cagr"] == pytest.approx(0.7 * expected_aaa)
    assert [item["ticker"] for item in result["excluded"]] == ["CCC"]
    assert result["excluded"][0]["weight"] == pytest.approx(0.1)


def test_forecast_prefers_published_thesis_and_publishable_model(db_session):
    aaa = _company(db_session, "AAA")
    _position(db_session, aaa, price=100, value=1000)
    _thesis(db_session, aaa, version=1, status="published", bear=90, base=150, bull=200)
    _thesis(db_session, aaa, version=2, status="draft", bear=1, base=1, bull=1)
    _model(db_session, aaa, version=1, horizon=5, publishable=True)
    _model(db_session, aaa, version=2, horizon=30, publishable=False)
    db_session.commit()

    result = portfolio_forecast(db=db_session)
    item = result["positions"][0]
    assert item["thesis_version"] == 1
    assert item["thesis_status"] == "published"
    assert item["model_version"] == 1
    assert item["horizon_years"] == 5
    assert item["cagr"]["base"] == pytest.approx(1.5**0.2 - 1)


def test_forecast_falls_back_to_model_probabilities(db_session):
    aaa = _company(db_session, "AAA")
    _position(db_session, aaa, price=100, value=1000)
    _thesis(db_session, aaa, version=1, status="published", bear=100, base=100, bull=200)
    _model(db_session, aaa, version=1, horizon=5, probs={"bull": 1.0})
    db_session.commit()

    result = portfolio_forecast(db=db_session)
    item = result["positions"][0]
    assert item["probabilities"] == {"bull": 1.0}
    assert item["expected_cagr"] == pytest.approx(2**0.2 - 1)


def test_forecast_defaults_horizon_without_model(db_session):
    aaa = _company(db_session, "AAA")
    _position(db_session, aaa, price=100, value=1000)
    _thesis(db_session, aaa, version=1, status="published", bear=90, base=150, bull=200)
    db_session.commit()

    result = portfolio_forecast(db=db_session)
    item = result["positions"][0]
    assert item["horizon_years"] == 5
    assert item["model_version"] is None


def test_forecast_empty_portfolio(db_session):
    result = portfolio_forecast(db=db_session)
    assert result["portfolio"] is None
    assert result["positions"] == []
    assert result["excluded"] == []

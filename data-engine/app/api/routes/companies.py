from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import (
    CalculatedMetric,
    Company,
    CompanyKPI,
    DecisionLesson,
    FinancialFact,
    FundamentalDriver,
    ManagementPromise,
)
from app.schemas import (
    CalculatedMetricOut,
    CalculatedMetricsResponse,
    CompanyOut,
    CompanyKPIOut,
    CompanySnapshotOut,
    FinancialFactOut,
    FinancialRefreshResponse,
)
from app.services.connectors.fmp import FMPClient
from app.services.financial_ingestion_service import FinancialIngestionService
from app.services.fundamental_review_service import (
    DecisionJournalService,
    ExpectationRealityService,
)
from app.services.fundamental_model_repository import FundamentalModelRepository
from app.services.metric_calculation_service import MetricCalculationService
from app.services.moat_service import MoatService
from app.services.long_term_model_service import LongTermModelService
from app.services.peer_analysis_service import PeerAnalysisService
from app.services.peer_comparison_service import DEFAULT_PEER_METRICS, PeerComparisonService
from app.services.red_team_service import RedTeamService
from app.services.wacc_input_service import WaccInputService
from app.services.company_snapshot_service import CompanySnapshotService
from app.services.kpi_extraction_service import CompanyKPIRegistryService
from app.services.driver_assumption_service import (
    DriverAssumptionService,
    driver_assumption_payload,
)
from app.services.decision_learning_service import (
    DECISION_ERROR_TAXONOMY,
    DecisionLearningService,
)
from app.services.financial_terminal_service import FinancialTerminalService
from app.services.management_credibility_service import ManagementCredibilityService

router = APIRouter()


@router.get("/{ticker}/kpi-registry", response_model=list[CompanyKPIOut])
def company_kpi_registry(
    ticker: str, db: Session = Depends(get_db)
) -> list[CompanyKPI]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return list(
        db.scalars(
            select(CompanyKPI)
            .where(CompanyKPI.company_id == company.id, CompanyKPI.active.is_(True))
            .order_by(CompanyKPI.required.desc(), CompanyKPI.metric_key)
        ).all()
    )


@router.post("/{ticker}/kpi-registry/sync", response_model=list[CompanyKPIOut])
def sync_company_kpi_registry(
    ticker: str, db: Session = Depends(get_db)
) -> list[CompanyKPI]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyKPIRegistryService().sync(db, company)


class CompanyEnsureRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.\-]+$")
    name: str | None = Field(default=None, max_length=255)
    exchange: str | None = Field(default=None, max_length=50)
    currency: str | None = Field(default=None, min_length=3, max_length=10)
    sector: str | None = Field(default=None, max_length=120)
    industry: str | None = Field(default=None, max_length=160)


class DecisionJournalCreate(BaseModel):
    decision: Literal["buy", "hold", "trim", "sell", "watch", "avoid"]
    rationale: str = Field(min_length=5, max_length=5000)
    what_must_be_true: list[str] = Field(default_factory=list, max_length=30)


class DriverAssumptionCreate(BaseModel):
    driver_key: str = Field(min_length=1, max_length=160)
    fiscal_year: int = Field(ge=1900, le=2200)
    scenario: Literal["bear", "base", "bull"] = "base"
    value: Decimal
    source: str = Field(min_length=1, max_length=240)
    user_override: bool = True
    confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=5000)


class DecisionLessonUpdate(BaseModel):
    taxonomy: Literal[
        "overestimating_TAM",
        "underestimating_dilution",
        "extrapolating_peak_margin",
        "ignoring_balance_sheet",
        "management_trust_error",
        "valuation_anchoring",
        "position_sizing_error",
        "selling_too_early",
        "ignoring_cyclicality",
        "thesis_drift",
    ]
    cause: str = Field(min_length=3, max_length=5000)
    error: str = Field(min_length=3, max_length=5000)
    lesson: str = Field(min_length=3, max_length=5000)
    future_application: str = Field(min_length=3, max_length=5000)


class DecisionLessonAction(BaseModel):
    action: Literal["approve", "reject"]


class ManagementPromiseCreate(BaseModel):
    promise: str = Field(min_length=3, max_length=5000)
    promise_date: date
    expected_period: str = Field(min_length=1, max_length=80)
    metric: str | None = Field(default=None, max_length=160)
    operator: Literal[">", ">=", "<", "<=", "=="] | None = None
    target_value: Decimal | None = None
    unit: str | None = Field(default=None, max_length=40)
    source_document_id: int | None = None


class ManagementExplanationUpdate(BaseModel):
    explanation: str = Field(min_length=3, max_length=5000)


@router.post("/ensure", response_model=CompanyOut)
def ensure_company(payload: CompanyEnsureRequest, db: Session = Depends(get_db)) -> Company:
    ticker = payload.ticker.strip().upper()
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    if company is None:
        company = Company(
            ticker=ticker,
            name=(payload.name or ticker).strip(),
            exchange=(payload.exchange or "UNKNOWN").strip().upper(),
            currency=(payload.currency or "USD").strip().upper(),
            sector=(payload.sector or "Unknown").strip(),
            industry=(payload.industry or "Unknown").strip(),
            company_type="research_candidate",
            valuation_model="unassigned",
            special_sources=[],
            special_risks=[],
            factor_tags=[],
        )
        db.add(company)
    else:
        if payload.name and company.name == company.ticker:
            company.name = payload.name.strip()
        if payload.exchange and company.exchange == "UNKNOWN":
            company.exchange = payload.exchange.strip().upper()
        if payload.sector and company.sector == "Unknown":
            company.sector = payload.sector.strip()
        if payload.industry and company.industry == "Unknown":
            company.industry = payload.industry.strip()
    db.commit()
    db.refresh(company)
    return company


@router.get("", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)) -> list[Company]:
    return list(db.scalars(select(Company).order_by(Company.ticker)).all())


@router.get("/{ticker}", response_model=CompanyOut)
def get_company(ticker: str, db: Session = Depends(get_db)) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.get("/{ticker}/facts", response_model=list[FinancialFactOut])
def list_financial_facts(
    ticker: str,
    metric: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[FinancialFact]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    query = select(FinancialFact).where(FinancialFact.company_id == company.id)
    if metric:
        query = query.where(FinancialFact.metric == metric)
    query = query.order_by(
        FinancialFact.fiscal_year.desc().nullslast(),
        desc(FinancialFact.created_at),
    ).limit(limit)
    return list(db.scalars(query).all())


@router.get("/{ticker}/financial-terminal")
def financial_terminal(
    ticker: str,
    metrics: str | None = None,
    years: int = Query(default=10, ge=1, le=20),
    periodicity: Literal["all", "annual", "quarterly"] = "all",
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    requested = (
        [item.strip() for item in metrics.split(",") if item.strip()]
        if metrics
        else None
    )
    return FinancialTerminalService().build(
        db,
        company,
        metrics=requested,
        years=years,
        periodicity=periodicity,
    )


@router.get("/{ticker}/metrics/calculated", response_model=CalculatedMetricsResponse)
def list_calculated_metrics(
    ticker: str,
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    metrics = list(
        db.scalars(
            select(CalculatedMetric)
            .where(CalculatedMetric.company_id == company.id)
            .order_by(
                CalculatedMetric.fiscal_year.desc().nullslast(),
                desc(CalculatedMetric.created_at),
            )
        ).all()
    )
    return {
        "ticker": company.ticker,
        "status": "persisted" if metrics else "not_generated",
        "metrics": [
            CalculatedMetricOut(
                id=result.id,
                company_id=company.id,
                metric=result.metric,
                value=result.value,
                unit=result.unit,
                period=result.period,
                fiscal_year=result.fiscal_year,
                fiscal_quarter=result.fiscal_quarter,
                status=result.status,
                definition_version=result.definition_version,
                formula=result.formula,
                numerator=result.numerator,
                denominator=result.denominator,
                source_fact_ids=result.source_fact_ids,
                calculation_trace=result.calculation_trace,
                confidence=result.confidence,
            )
            for result in metrics
        ],
    }


@router.post("/{ticker}/metrics/refresh", response_model=CalculatedMetricsResponse)
def refresh_calculated_metrics(
    ticker: str,
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    metrics = MetricCalculationService().calculate_all(db, company, persist=True)
    return {
        "ticker": company.ticker,
        "status": "calculated",
        "metrics": [
            CalculatedMetricOut(
                id=result.id,
                company_id=company.id,
                metric=result.metric,
                value=result.value,
                unit=result.unit,
                period=result.period,
                fiscal_year=result.fiscal_year,
                fiscal_quarter=result.fiscal_quarter,
                status=result.status,
                definition_version=result.definition_version,
                formula=result.formula,
                numerator=result.numerator,
                denominator=result.denominator,
                source_fact_ids=result.source_fact_ids,
                calculation_trace=result.calculation_trace,
                confidence=result.confidence,
            )
            for result in metrics
        ],
    }


@router.get("/{ticker}/long-term-model")
def long_term_model(
    ticker: str,
    db: Session = Depends(get_db),
) -> dict:
    """Return the source-aware 5–10 year fundamental model for a company."""
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    payload = FundamentalModelRepository().latest_payload(db, company)
    return payload if payload else {
        "ticker": company.ticker,
        "status": "not_generated",
        "publishable": False,
    }


@router.post("/{ticker}/long-term-model/generate")
def generate_long_term_model(
    ticker: str,
    horizon: int = Query(default=5, ge=5, le=10),
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return LongTermModelService().build(db, company, horizon=horizon)


@router.get("/{ticker}/driver-assumptions")
def list_driver_assumptions(
    ticker: str,
    driver_key: str | None = None,
    scenario: Literal["bear", "base", "bull"] | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    versions = DriverAssumptionService().list(
        db, company, driver_key=driver_key, scenario=scenario
    )
    driver_keys = {
        driver.id: driver.driver_key
        for driver in db.scalars(
            select(FundamentalDriver).where(
                FundamentalDriver.id.in_({version.driver_id for version in versions})
            )
        ).all()
    } if versions else {}
    return [
        driver_assumption_payload(
            version, driver_key=driver_keys.get(version.driver_id)
        )
        for version in versions
    ]


@router.post("/{ticker}/driver-assumptions", status_code=201)
def create_driver_assumption(
    ticker: str,
    payload: DriverAssumptionCreate,
    horizon: int = Query(default=5, ge=5, le=10),
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        version = DriverAssumptionService().create(
            db,
            company,
            driver_key=payload.driver_key,
            fiscal_year=payload.fiscal_year,
            scenario=payload.scenario,
            value=payload.value,
            source=payload.source,
            user_override=payload.user_override,
            confidence=payload.confidence,
            rationale=payload.rationale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    model = LongTermModelService().build(db, company, horizon=horizon)
    return {
        "assumption": driver_assumption_payload(version, driver_key=payload.driver_key),
        "model_version": model.get("persistence"),
    }


@router.get("/{ticker}/snapshot", response_model=CompanySnapshotOut)
def company_snapshot(
    ticker: str,
    db: Session = Depends(get_db),
) -> CompanySnapshotOut:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanySnapshotService().build(db, company)


@router.post("/{ticker}/snapshot/refresh", response_model=CompanySnapshotOut)
def refresh_company_snapshot(
    ticker: str,
    horizon: int = Query(default=5, ge=5, le=10),
    db: Session = Depends(get_db),
) -> CompanySnapshotOut:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    MetricCalculationService().calculate_all(db, company, persist=True)
    LongTermModelService().build(db, company, horizon=horizon)
    MoatService().assess(db, company, persist=True)
    return CompanySnapshotService().build(db, company)


@router.get("/{ticker}/decision-journal")
def decision_journal(ticker: str, db: Session = Depends(get_db)) -> list[dict]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return [_decision_payload(entry) for entry in DecisionJournalService().list(db, company)]


@router.post("/{ticker}/decision-journal", status_code=201)
def create_decision_journal_entry(
    ticker: str,
    payload: DecisionJournalCreate,
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    entry = DecisionJournalService().create(
        db,
        company,
        decision=payload.decision,
        rationale=payload.rationale,
        what_must_be_true=[item.strip() for item in payload.what_must_be_true if item.strip()],
    )
    return _decision_payload(entry)


@router.get("/{ticker}/decision-lessons/taxonomy")
def decision_lesson_taxonomy(ticker: str, db: Session = Depends(get_db)) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"taxonomy": sorted(DECISION_ERROR_TAXONOMY)}


@router.get("/{ticker}/decision-lessons")
def decision_lessons(ticker: str, db: Session = Depends(get_db)) -> list[dict]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return [
        DecisionLearningService.payload(item)
        for item in DecisionLearningService.list(db, company)
    ]


@router.post("/{ticker}/decision-lessons/propose")
def propose_decision_lessons(
    ticker: str, db: Session = Depends(get_db)
) -> list[dict]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return [
        DecisionLearningService.payload(item)
        for item in DecisionLearningService().propose_from_reviews(db, company)
    ]


@router.put("/{ticker}/decision-lessons/{lesson_id}")
def update_decision_lesson(
    ticker: str,
    lesson_id: int,
    payload: DecisionLessonUpdate,
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    lesson = db.get(DecisionLesson, lesson_id)
    if not company or not lesson or lesson.company_id != company.id:
        raise HTTPException(status_code=404, detail="Decision lesson not found")
    try:
        item = DecisionLearningService().update(
            db,
            lesson,
            taxonomy=payload.taxonomy,
            cause=payload.cause,
            error=payload.error,
            lesson_text=payload.lesson,
            future_application=payload.future_application,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return DecisionLearningService.payload(item)


@router.post("/{ticker}/decision-lessons/{lesson_id}/action")
def decide_decision_lesson(
    ticker: str,
    lesson_id: int,
    payload: DecisionLessonAction,
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    lesson = db.get(DecisionLesson, lesson_id)
    if not company or not lesson or lesson.company_id != company.id:
        raise HTTPException(status_code=404, detail="Decision lesson not found")
    try:
        item = DecisionLearningService().decide(
            db,
            lesson,
            action=payload.action,
            actor=str(db.info.get("user_id") or "local-user"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return DecisionLearningService.payload(item)


@router.get("/{ticker}/management-credibility")
def management_credibility(ticker: str, db: Session = Depends(get_db)) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return ManagementCredibilityService().dashboard(db, company)


@router.post("/{ticker}/management-credibility/promises", status_code=201)
def register_management_promise(
    ticker: str,
    payload: ManagementPromiseCreate,
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        row = ManagementCredibilityService().register(
            db, company, **payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ManagementCredibilityService.payload(row)


@router.post("/{ticker}/management-credibility/import-call-claims")
def import_management_call_claims(
    ticker: str, db: Session = Depends(get_db)
) -> list[dict]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return [
        ManagementCredibilityService.payload(row)
        for row in ManagementCredibilityService().import_call_claims(db, company)
    ]


@router.post("/{ticker}/management-credibility/reconcile")
def reconcile_management_promises(
    ticker: str, db: Session = Depends(get_db)
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    ManagementCredibilityService().reconcile(db, company)
    return ManagementCredibilityService().dashboard(db, company)


@router.put("/{ticker}/management-credibility/promises/{promise_id}/explanation")
def update_management_explanation(
    ticker: str,
    promise_id: int,
    payload: ManagementExplanationUpdate,
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    promise = db.get(ManagementPromise, promise_id)
    if not company or not promise or promise.company_id != company.id:
        raise HTTPException(status_code=404, detail="Management promise not found")
    row = ManagementCredibilityService().set_explanation(
        db, promise, payload.explanation
    )
    return ManagementCredibilityService.payload(row)


@router.get("/{ticker}/expectation-reality")
def expectation_reality(ticker: str, db: Session = Depends(get_db)) -> list[dict]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return [_expectation_payload(item) for item in ExpectationRealityService().list(db, company)]


@router.post("/{ticker}/expectation-reality/review")
def review_expectation_reality(
    ticker: str,
    db: Session = Depends(get_db),
) -> list[dict]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return [_expectation_payload(item) for item in ExpectationRealityService().review(db, company)]


def _decision_payload(entry) -> dict:
    return {
        "id": entry.id,
        "thesis_version_id": entry.thesis_version_id,
        "model_version_id": entry.model_version_id,
        "decision_date": entry.decision_date,
        "decision": entry.decision,
        "rationale": entry.rationale,
        "what_must_be_true": entry.what_must_be_true,
        "price": entry.price,
        "status": entry.status,
        "metadata": entry.metadata_,
    }


def _expectation_payload(item) -> dict:
    return {
        "id": item.id,
        "model_version_id": item.model_version_id,
        "forecast_id": item.forecast_id,
        "actual_fact_id": item.actual_fact_id,
        "actual_metric_id": item.actual_metric_id,
        "actual_source_type": item.actual_source_type,
        "semantics": item.semantics,
        "fiscal_year": item.fiscal_year,
        "metric": item.metric,
        "expected_value": item.expected_value,
        "actual_value": item.actual_value,
        "variance": item.variance,
        "variance_percent": item.variance_percent,
        "status": item.status,
        "reviewed_at": item.reviewed_at,
        "trace": item.trace,
    }


@router.get("/{ticker}/peers/comparison")
def peer_comparison(
    ticker: str,
    limit: int = Query(default=8, ge=1, le=20),
    refresh: bool = Query(default=False),
    metrics: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    metric_names = [item.strip() for item in metrics.split(",") if item.strip()] if metrics else DEFAULT_PEER_METRICS
    return PeerComparisonService().compare(
        db,
        company,
        limit=limit,
        metrics=metric_names,
        refresh=refresh,
    )


@router.get("/{ticker}/peers/analysis")
def peer_analysis(
    ticker: str,
    limit: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return PeerAnalysisService().analyze(db, company, limit=limit)


@router.get("/{ticker}/moat")
def moat_assessment(
    ticker: str,
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return MoatService().read(db, company)


@router.post("/{ticker}/moat/refresh")
def refresh_moat_assessment(
    ticker: str,
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return MoatService().assess(db, company, persist=True)


@router.post("/{ticker}/red-team")
def run_red_team(ticker: str, db: Session = Depends(get_db)) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    run = RedTeamService().run(db, company)
    return _red_team_payload(run)


@router.get("/{ticker}/red-team/latest")
def latest_red_team(ticker: str, db: Session = Depends(get_db)) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    run = RedTeamService().latest(db, company)
    if not run:
        raise HTTPException(status_code=404, detail="No red-team run found")
    return _red_team_payload(run)


def _red_team_payload(run) -> dict:
    return {
        "id": run.id,
        "company_id": run.company_id,
        "thesis_version_id": run.thesis_version_id,
        "status": run.status,
        "score": run.score,
        "strongest_bear_case": run.strongest_bear_case,
        "findings": run.findings,
        "broken_assumptions": run.broken_assumptions,
        "missing_risks": run.missing_risks,
        "falsification_tests": run.falsification_tests,
        "model": run.model,
        "prompt_version": run.prompt_version,
        "trace": run.trace,
        "created_at": run.created_at,
    }


@router.post("/{ticker}/refresh/fmp", response_model=FinancialRefreshResponse)
async def refresh_fmp_financials(ticker: str, db: Session = Depends(get_db)) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    try:
        return await FinancialIngestionService().refresh_from_fmp(
            db=db,
            company=company,
            client=FMPClient(),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc


@router.post("/{ticker}/refresh/sec", response_model=FinancialRefreshResponse)
async def refresh_sec_financials(ticker: str, db: Session = Depends(get_db)) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return await FinancialIngestionService().refresh_from_sec(db=db, company=company)
    except RuntimeError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc


@router.post("/{ticker}/refresh/wacc")
async def refresh_wacc_inputs(
    ticker: str, db: Session = Depends(get_db)
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return await WaccInputService().refresh(db, company)
    except RuntimeError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc

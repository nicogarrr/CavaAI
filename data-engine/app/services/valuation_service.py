"""Company valuation orchestration — engine registry, no bootstrap fair values."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, MarketPrice, Position, ValuationModel, ValuationOutput
from app.valuation.engines import resolve, resolve_engine_key
from app.valuation.engines.base import MODEL_VERSION, apply_publication_blockers
from app.valuation.point_in_time import (
    assert_fiscal_year_no_lookahead,
    assert_no_lookahead,
)


def _free_data_trace(db: Session, company: Company) -> dict | None:
    """Best-effort: expone metadata.free_data.recent_filings en el trace.

    Lee los Document de la compañía y devuelve los recent_filings del
    primero que los tenga. Nunca lanza excepciones.
    """
    try:
        from app.models import Document

        docs = list(
            db.scalars(
                select(Document).where(Document.company_id == company.id).limit(20)
            ).all()
        )
        for doc in docs:
            meta = getattr(doc, "metadata_", None) or {}
            free_data = meta.get("free_data") or {}
            recent_filings = free_data.get("recent_filings") or []
            if recent_filings:
                return {"recent_filings": recent_filings}
        return None
    except Exception:
        return None


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _require_as_of(value: object) -> date:
    parsed = _as_date(value)
    if parsed is None:
        raise ValueError(f"Valuation as_of must be an ISO date, got {value!r}")
    return parsed


def _assert_no_lookahead_guard(
    valuation: dict, *, as_of: date | None = None
) -> None:
    """Fail closed when valuation trace metadata contains future periods.

    ``as_of`` defaults to a date carried by the valuation/trace, then to today.
    Unknown period formats are ignored; recognised exact dates and fiscal years
    are delegated to the public point-in-time guard contract.
    """
    trace = valuation.get("trace") or {}
    if not isinstance(trace, Mapping):
        return

    requested_as_of = as_of if as_of is not None else valuation.get("as_of")
    if requested_as_of is None:
        requested_as_of = trace.get("as_of")
    cutoff = _require_as_of(requested_as_of) if requested_as_of is not None else date.today()

    periods: dict[str, object] = {}
    raw_periods = trace.get("periods")
    if isinstance(raw_periods, Mapping):
        periods.update({str(label): value for label, value in raw_periods.items()})

    snapshot = trace.get("snapshot")
    if isinstance(snapshot, Mapping):
        for key in ("as_of", "income_statement", "balance_sheet", "shares"):
            if snapshot.get(key) is not None:
                periods.setdefault(f"snapshot.{key}", snapshot[key])

    for label, raw_period in periods.items():
        exact_date = _as_date(raw_period)
        if exact_date is not None:
            assert_no_lookahead(
                as_of=cutoff,
                data_date=exact_date,
                label=f"valuation {label}",
            )
            continue
        if not isinstance(raw_period, str):
            continue
        match = re.search(r"(?<!\d)(?:FY\s*)?(\d{4})(?!\d)", raw_period, re.IGNORECASE)
        if match is None:
            continue
        assert_fiscal_year_no_lookahead(
            as_of=cutoff,
            fiscal_year=int(match.group(1)),
            label=f"valuation {label} {raw_period}",
        )


def _position_price(db: Session, company_id: int) -> float | None:
    """Return a real market price or None. Never invent a placeholder price."""
    position = db.scalar(select(Position).where(Position.company_id == company_id).limit(1))
    if position and position.market_price and float(position.market_price) > 0:
        return float(position.market_price)
    market_price = db.scalar(
        select(MarketPrice)
        .where(MarketPrice.company_id == company_id)
        .order_by(desc(MarketPrice.date))
        .limit(1)
    )
    if market_price and market_price.close and float(market_price.close) > 0:
        return float(market_price.close)
    return None


class ValuationService:
    def value_company(
        self, db: Session, company: Company, *, as_of: date | None = None
    ) -> dict:
        current_price = _position_price(db, company.id)
        engine = resolve(company)
        context = engine.build_context(db, company, current_price)
        # Blocker enforcement lives here as well as in the engines: this is the
        # function every consumer goes through (thesis, red team, snapshot,
        # persistence), and a result that carries publication blockers must
        # never reach them labelled as a final valuation.
        result = apply_publication_blockers(engine.value(context))

        # Ensure contract fields always present for API / thesis consumers.
        result.setdefault("status", "ok")
        result.setdefault("publishable", result.get("status") == "ok")
        result.setdefault("missing_inputs", [])
        result.setdefault("reverse_dcf", {})
        result.setdefault("sensitivity", {"rows": []})
        result.setdefault("moat", {})
        try:
            from app.services.moat_service import MoatService

            result["moat"] = MoatService().assess(
                db, company, persist=False
            )
        except Exception as exc:
            result["moat"] = {
                "status": "unavailable",
                "moats": [],
                "error": str(exc),
            }
        result["trace"] = result.get("trace") or {}
        result["trace"].setdefault("engine", resolve_engine_key(company))
        result["trace"].setdefault("model_version", MODEL_VERSION)
        result["trace"]["resolved_engine"] = resolve_engine_key(company)
        free_data = _free_data_trace(db, company)
        if free_data is not None:
            result["trace"]["free_data"] = free_data
        _assert_no_lookahead_guard(result, as_of=as_of)

        if current_price is None:
            result["trace"]["price_status"] = "missing_market_price"
            if result.get("margin_of_safety") is not None:
                # Keep MOS only when price exists; engines already return None.
                pass
            if result.get("status") == "ok" and result.get("publishable"):
                # Values may exist but MOS / reverse DCF incomplete without price.
                result["trace"]["incomplete_without_price"] = True
        else:
            result["trace"]["price_status"] = "ok"

        return result

    def persist_output(
        self,
        db: Session,
        company: Company,
        valuation: dict,
        *,
        commit: bool = True,
    ) -> ValuationModel | None:
        if not valuation.get("publishable") and valuation.get("status") == "insufficient_data":
            # Persist a draft trace so audits can show why valuation was blocked.
            status = "insufficient_data"
        else:
            status = "final" if valuation.get("publishable") else "draft"

        latest = db.scalar(
            select(ValuationModel)
            .where(ValuationModel.company_id == company.id)
            .order_by(desc(ValuationModel.version))
            .limit(1)
        )
        version = (latest.version + 1) if latest else 1
        model = ValuationModel(
            company_id=company.id,
            model_type=valuation.get("model_type") or company.valuation_model,
            version=version,
            status=status,
            calculation_trace=valuation.get("trace") or {},
        )
        db.add(model)
        db.flush()

        for scenario, key in [("bear", "bear_value"), ("base", "base_value"), ("bull", "bull_value")]:
            raw = valuation.get(key)
            if raw is None:
                continue
            db.add(
                ValuationOutput(
                    valuation_model_id=model.id,
                    scenario=scenario,
                    value_per_share=Decimal(str(raw)),
                    output_payload=valuation,
                )
            )
        if commit:
            db.commit()
            db.refresh(model)
        else:
            db.flush()
        return model
